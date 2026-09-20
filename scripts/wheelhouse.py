"""wheelhouse-req.txt / wheelhouse/ 的可复现生成与一致性校验。

为什么需要这个脚本
------------------
backend/Dockerfile 用「预置 wheelhouse + ``uv pip install -r wheelhouse-req.txt --offline``」
装依赖（原因见该文件注释）。这里有个**静默故障**风险：

    pyproject.toml 加了依赖 → uv.lock 变了 → 但 wheelhouse-req.txt 忘了重新导出
    → 镜像**构建成功**（清单里没有那个包，离线安装自然不报错）
    → 应用启动后才 ImportError

构建失败能当场发现，这种漂移不会。所以必须有 ``check`` 把它变成显式错误。

子命令
------
    python scripts/wheelhouse.py check     # 清单是否与 uv.lock 一致（并对 wheelhouse/ 做哈希校验）
    python scripts/wheelhouse.py update    # 重新导出清单（已过滤 win32 包）+ 补下缺失的 wheel

两条命令都必须在**仓库根**执行（uv.lock / wheelhouse-req.txt / wheelhouse/ 都在根目录）。

为什么不用 ``uv pip download``
------------------------------
uv 没有 download 子命令，所以 update 借 ``uv run --no-project --with pip python -m pip download``
执行 —— 遵守项目「禁止裸 python/pip」的规则（不碰全局环境）。
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import subprocess
import sys
import tempfile
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_FILE = REPO_ROOT / "wheelhouse-req.txt"
WHEELHOUSE_DIR = REPO_ROOT / "wheelhouse"

# uv export 的参数（与 Dockerfile 注释里记录的一致）。
# `--no-emit-package app` 必须加：否则首行是 `-e ./backend`，pip 会报
# "editable requirement ... cannot be installed when requiring hashes"。
EXPORT_ARGS: tuple[str, ...] = (
    "export",
    "--frozen",
    "--all-extras",
    "--no-dev",
    "--package",
    "app",
    "--format",
    "requirements.txt",
    "--no-emit-package",
    "app",
)

# win32 专属包：pip 跨平台下载时按**本机**环境评估标记，这些行会让 pip 直接报错；
# 目标镜像是 linux，它们在容器里永远不会被安装 → 从清单里整体删除。
EXCLUDED_PACKAGES = frozenset({"colorama", "pywin32", "tzdata"})

# 在 PyPI 只提供 sdist（没有 wheel）的包：下载时必须换 --no-binary，
# 否则 --only-binary=:all: 会报 "No matching distribution found"。
# antlr4-python3-runtime 4.9.* 只有 .tar.gz（omegaconf 的传递依赖，被 rapidocr 引入；
# omegaconf 把版本卡在 ==4.9.*，升不上去）。
SDIST_ONLY_PACKAGES = frozenset({"jieba", "antlr4-python3-runtime"})

# 目标运行平台：镜像 base 是 python:3.13-slim（linux amd64）。
# 列多个 manylinux 标签是为了覆盖各包声明的不同 GLIBC 基线（旧标签 pip 仍接受）。
TARGET_PLATFORMS: tuple[str, ...] = (
    "manylinux2014_x86_64",
    "manylinux_2_28_x86_64",
    "manylinux_2_27_x86_64",
    "manylinux_2_26_x86_64",
    "manylinux_2_17_x86_64",
)
TARGET_PYTHON_VERSION = "3.13"
PYPI_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"

_REQUIREMENT_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)(?:\s*;\s*(.+?))?\s*\\?\s*$"
)
_ARTIFACT_NAME_RE = re.compile(r"^(?P<name>.+?)-(?P<version>[0-9][^-]*)")
_ARTIFACT_SUFFIXES: tuple[str, ...] = (".whl", ".tar.gz", ".zip", ".tar.bz2")


@dataclass(frozen=True)
class RequirementBlock:
    """清单里的一个包声明块：一行 ``name==version [; marker]`` + 若干 ``--hash`` 续行。"""

    name: str  # 规范化包名（PEP 503）
    version: str
    marker: str
    hashes: tuple[str, ...]  # 形如 "sha256:abcd..."，含算法前缀


# --------------------------------------------------------------------------------------
# 纯函数：解析
# --------------------------------------------------------------------------------------


def normalize_name(name: str) -> str:
    """PEP 503 规范化：小写 + 把 ``-``/``_``/``.`` 统一成 ``-``（faiss_cpu → faiss-cpu）。"""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirement_line(line: str) -> tuple[str, str, str] | None:
    """把 ``name==version[ ; marker] [\\]`` 拆成 ``(规范化包名, 版本, 标记)``。

    非包声明行（空行 / ``#`` 注释 / ``--hash`` / ``--index-url`` 等）返回 None。
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "-")):
        return None
    match = _REQUIREMENT_RE.match(stripped)
    if not match:
        return None
    name, version, marker = match.groups()
    return normalize_name(name), version, (marker or "").strip()


def parse_blocks(text: str) -> list[RequirementBlock]:
    """解析出所有包声明块（供哈希比对与下载清单复用）。"""
    blocks: list[RequirementBlock] = []
    name: str | None = None
    version = ""
    marker = ""
    hashes: list[str] = []

    def flush() -> None:
        if name is not None:
            blocks.append(RequirementBlock(name, version, marker, tuple(hashes)))

    for line in text.splitlines():
        parsed = parse_requirement_line(line)
        if parsed is not None:
            flush()
            name, version, marker = parsed
            hashes = []
            continue
        stripped = line.strip()
        if name is not None and stripped.startswith("--hash="):
            hashes.append(stripped[len("--hash=") :].rstrip(" \\"))
    flush()
    return blocks


def parse_artifact_filename(filename: str) -> tuple[str, str] | None:
    """从 wheel / sdist 文件名解析 ``(规范化包名, 版本)``，无法解析返回 None。

    例：``faiss_cpu-1.15.0-cp310-abi3-manylinux...whl`` → ``("faiss-cpu", "1.15.0")``
        ``jieba-0.42.1.tar.gz``                        → ``("jieba", "0.42.1")``
    """
    for suffix in _ARTIFACT_SUFFIXES:
        if not filename.endswith(suffix):
            continue
        match = _ARTIFACT_NAME_RE.match(filename[: -len(suffix)])
        if match is None:
            return None
        return normalize_name(match.group("name")), match.group("version")
    return None


# --------------------------------------------------------------------------------------
# 纯函数：变换与比对
# --------------------------------------------------------------------------------------


def strip_banner(text: str) -> str:
    """去掉文件顶部 uv 自动生成的注释横幅。

    横幅里写着当时的 ``-o`` 路径（和 uv 版本），与依赖内容无关 —— 逐字节比对必须忽略它，
    否则换个输出文件名就会误报「清单不一致」。
    """
    lines = text.splitlines(keepends=True)
    index = 0
    while index < len(lines) and lines[index].lstrip().startswith("#"):
        index += 1
    return "".join(lines[index:])


def strip_excluded_packages(
    text: str, excluded: Collection[str] = EXCLUDED_PACKAGES
) -> str:
    """删除指定包（连同其 ``--hash`` 续行与 ``# via`` 注释行），其余字节原样保留。"""
    kept: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if skipping:
            # 块内所有后续行都是缩进的（--hash / # via / #   xxx）
            if line[:1] in (" ", "\t"):
                continue
            skipping = False
        parsed = parse_requirement_line(line)
        if parsed is not None and parsed[0] in excluded:
            skipping = True
            continue
        kept.append(line)
    return "".join(kept)


def render_requirements(
    exported_text: str, output_name: str = REQUIREMENTS_FILE.name
) -> str:
    """把 uv export 的原始输出渲染成仓库里提交的清单（规范化横幅 + 过滤 win32 包）。"""
    banner = (
        "# This file was autogenerated by uv via the following command:\n"
        f"#    uv {' '.join(EXPORT_ARGS)} -o {output_name}\n"
        "# ⚠️ 已删除 win32 专属包："
        f"{' / '.join(sorted(EXCLUDED_PACKAGES))}"
        "（目标镜像是 linux，见 scripts/wheelhouse.py）\n"
    )
    return banner + strip_excluded_packages(strip_banner(exported_text))


def render_download_requirements(blocks: Iterable[RequirementBlock]) -> str:
    """生成给 pip download 用的临时清单：**去掉环境标记**。

    原清单里 ``faiss-cpu==1.15.0 ; sys_platform != 'win32'`` 这类标记会被 pip 按
    **本机**（win32）评估 → 直接跳过 linux-only 包且不报错，wheelhouse 就悄悄缺件了。
    所以下载阶段一律去标记，改由 ``--platform`` 明确指定目标平台。
    """
    lines: list[str] = []
    for block in blocks:
        if not block.hashes:
            lines.append(f"{block.name}=={block.version}")
            continue
        lines.append(f"{block.name}=={block.version} \\")
        last = len(block.hashes) - 1
        for position, digest in enumerate(block.hashes):
            lines.append(f"    --hash={digest}{' \\' if position < last else ''}")
    return "\n".join(lines) + "\n"


def build_download_command(requirements_file: Path, *, binaries: bool) -> list[str]:
    """构造 pip download 命令（``binaries=False`` 时切到 sdist 模式，见 SDIST_ONLY_PACKAGES）。"""
    command = [
        "uv",
        "run",
        "--no-project",
        "--with",
        "pip",
        "python",
        "-m",
        "pip",
        "download",
        "-r",
        str(requirements_file),
        "-d",
        str(WHEELHOUSE_DIR),
        "--no-deps",
        "-i",
        PYPI_INDEX,
    ]
    if binaries:
        for platform_tag in TARGET_PLATFORMS:
            command += ["--platform", platform_tag]
        command += ["--python-version", TARGET_PYTHON_VERSION, "--only-binary=:all:"]
    else:
        command.append("--no-binary=:all:")
    return command


def check_wheelhouse(
    blocks: Sequence[RequirementBlock], artifacts: dict[str, str]
) -> list[str]:
    """比对清单与 wheelhouse/ 目录，返回问题列表（空列表 = 通过）。

    ``artifacts`` 是 ``{文件名: sha256 摘要}``（不带算法前缀），由调用方扫描目录得到，
    这样本函数保持纯函数、可单测。
    """
    problems: list[str] = []
    claimed: set[str] = set()
    index: dict[tuple[str, str], list[str]] = {}
    for filename in artifacts:
        key = parse_artifact_filename(filename)
        if key is None:
            problems.append(f"{filename}：文件名解析不出包名/版本，无法校验")
            claimed.add(filename)  # 已报过，不要再报成「残留」
            continue
        index.setdefault(key, []).append(filename)

    for block in blocks:
        filenames = index.get((block.name, block.version), [])
        if not filenames:
            problems.append(f"{block.name}=={block.version}：wheelhouse 里缺少对应文件")
            continue
        claimed.update(filenames)
        if block.hashes and not any(
            f"sha256:{artifacts[name]}" in block.hashes for name in filenames
        ):
            problems.append(
                f"{block.name}=={block.version}：文件哈希与清单不符（{', '.join(filenames)}）"
            )

    for filename in sorted(set(artifacts) - claimed):
        problems.append(f"{filename}：清单里没有对应条目（旧版本残留，应删除）")
    return problems


def missing_blocks(
    blocks: Sequence[RequirementBlock], artifacts: dict[str, str]
) -> list[RequirementBlock]:
    """挑出 wheelhouse/ 里没有对应文件的包（判断依据与 check_wheelhouse 同源）。"""
    present = {parse_artifact_filename(name) for name in artifacts}
    return [block for block in blocks if (block.name, block.version) not in present]


def unified_diff(
    expected_name: str, actual_name: str, expected: str, actual: str
) -> str:
    """生成统一格式差异文本（expected=仓库现状，actual=依据 uv.lock 重算的结果）。"""
    return "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=expected_name,
            tofile=actual_name,
        )
    )


# --------------------------------------------------------------------------------------
# 副作用：跑命令、读目录
# --------------------------------------------------------------------------------------


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_export(destination: Path) -> str:
    """在仓库根执行 uv export，返回导出文本。"""
    command = ["uv", *EXPORT_ARGS, "-o", str(destination)]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"uv export 失败（exit {result.returncode}）\n"
            f"命令：{' '.join(command)}\n{result.stderr.strip()}"
        )
    return destination.read_text(encoding="utf-8")


def collect_artifacts() -> dict[str, str]:
    """扫描 wheelhouse/，返回 ``{文件名: sha256}``；目录不存在时返回空字典。"""
    if not WHEELHOUSE_DIR.is_dir():
        return {}
    return {
        path.name: sha256_file(path)
        for path in sorted(WHEELHOUSE_DIR.iterdir())
        if path.is_file()
    }


def write_requirements(text: str) -> None:
    # newline="\n"：Windows 上禁止把 \n 翻成 \r\n，清单必须与 Linux 侧逐字节一致
    with REQUIREMENTS_FILE.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


# --------------------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------------------


def command_check() -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        exported = run_export(Path(tmp_dir) / REQUIREMENTS_FILE.name)

    expected = strip_excluded_packages(strip_banner(exported))
    committed = (
        strip_banner(REQUIREMENTS_FILE.read_text(encoding="utf-8"))
        if REQUIREMENTS_FILE.exists()
        else ""
    )

    if expected != committed:
        print(f"❌ {REQUIREMENTS_FILE.name} 与 uv.lock 不一致：")
        print(
            unified_diff(
                f"{REQUIREMENTS_FILE.name}（仓库现状）",
                f"{REQUIREMENTS_FILE.name}（依据 uv.lock 重算）",
                committed,
                expected,
            )
        )
        print("   修复：在仓库根执行 `python scripts/wheelhouse.py update`")
        return 1
    print(
        f"✅ {REQUIREMENTS_FILE.name} 与 uv.lock 一致（{len(parse_blocks(committed))} 个包）"
    )

    artifacts = collect_artifacts()
    if not artifacts:
        print(
            "ℹ️ wheelhouse/ 不存在或为空（被 gitignore，可用 update 生成）→ 跳过轮子校验"
        )
        return 0

    problems = check_wheelhouse(parse_blocks(committed), artifacts)
    if problems:
        print(f"❌ wheelhouse/ 校验未通过（{len(problems)} 项）：")
        for problem in problems:
            print(f"   - {problem}")
        print("   修复：跑 `python scripts/wheelhouse.py update` 补齐，并删除残留文件")
        return 1
    print(f"✅ wheelhouse/ 校验通过（{len(artifacts)} 个文件，哈希全部匹配）")
    return 0


def command_update() -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        exported = run_export(Path(tmp_dir) / REQUIREMENTS_FILE.name)

    rendered = render_requirements(exported)
    current = (
        REQUIREMENTS_FILE.read_text(encoding="utf-8")
        if REQUIREMENTS_FILE.exists()
        else None
    )
    if current == rendered:
        print(f"ℹ️ {REQUIREMENTS_FILE.name} 无变化")
    else:
        write_requirements(rendered)
        print(f"✅ 已更新 {REQUIREMENTS_FILE.name}")

    blocks = parse_blocks(rendered)
    missing = missing_blocks(blocks, collect_artifacts())
    if not missing:
        print("✅ wheelhouse/ 已完整，无需下载")
        return 0

    print(f"⬇️ wheelhouse/ 缺 {len(missing)} 个包：{'、'.join(b.name for b in missing)}")
    binary = [b for b in missing if b.name not in SDIST_ONLY_PACKAGES]
    sdist = [b for b in missing if b.name in SDIST_ONLY_PACKAGES]
    WHEELHOUSE_DIR.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        for group, use_binaries in ((binary, True), (sdist, False)):
            if not group:
                continue
            manifest = (
                Path(tmp_dir) / f"download-{'binary' if use_binaries else 'sdist'}.txt"
            )
            manifest.write_text(render_download_requirements(group), encoding="utf-8")
            command = build_download_command(manifest, binaries=use_binaries)
            print(f"   $ {' '.join(command)}")
            result = subprocess.run(command, cwd=REPO_ROOT)
            if result.returncode != 0:
                print(f"❌ pip download 失败（exit {result.returncode}）")
                return 1

    problems = check_wheelhouse(blocks, collect_artifacts())
    if problems:
        print("❌ 补下之后仍有问题：")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    print("✅ wheelhouse/ 已补齐且校验通过")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="wheelhouse-req.txt / wheelhouse/ 的可复现生成与一致性校验（在仓库根执行）"
    )
    parser.add_argument(
        "command",
        choices=("check", "update"),
        help="check：校验清单与 uv.lock 一致；update：重新导出清单并补齐缺失的 wheel",
    )
    args = parser.parse_args(argv)
    return command_check() if args.command == "check" else command_update()


if __name__ == "__main__":
    sys.exit(main())

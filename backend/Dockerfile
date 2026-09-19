# 🔴 必须与 backend/pyproject.toml 的 requires-python = ">=3.12,<4.0" 保持一致。
#    模板原本是 3.10，项目升级到 3.13 后此处未同步，导致 `uv sync` 报
#    "current Python version (3.10.x) is not compatible with the locked requirement"。
#    选 3.13 而非 3.12 的理由：本机 .venv 即 3.13.0，且 294 单测 + 18 集成测试
#    已在该版本上实跑通过 → 镜像与本地环境完全一致，避免"本地能跑、容器报错"。
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

# Compile bytecode
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

# uv Cache
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#caching
ENV UV_LINK_MODE=copy

# 🔑 国内 PyPI 镜像源（默认走 https://pypi.org/simple，实测本机约 4.5 KB/s）。
#
# 实测数据：不加镜像源时，1.2MB 的 pygments 下载耗时 264 秒，
# 整次依赖安装超过 20 分钟仍未完成；Docker Hub 基础层同样慢（236MB / 166 秒）。
# 这是网络环境问题，不是包本身的问题。
#
# 用清华源（Tuna）—— 国内最稳定的 PyPI 镜像之一，与 pypi.org 数据同步但不限速。
# ⚠️ 必须在所有 `uv sync` / `uv pip install` 之前声明，否则不生效。
# 如需换源（阿里云/腾讯云），只改这一行即可。
ENV UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

# 🔴🔴 关键：`UV_DEFAULT_INDEX` 管不到 uv.lock 里的**直链**
#
# uv.lock 为每个包记录了完整的 wheel URL，指向 files.pythonhosted.org：
#     wheels = [{ url = "https://files.pythonhosted.org/packages/30/e1/.../regex-...whl" }]
# `--frozen` 会**照这些 URL 原样下载**，索引镜像形同虚设。
#
# 实测（2026-09-17）：容器直连 files.pythonhosted.org 失败 ——
#     Failed to download `regex==2026.5.9`
#     client error (Connect)
#     invalid peer certificate: Other(OtherError(CaUsedAsEndEntity))
#   ↑ 中间人代理把根 CA 当服务器证书下发，证书链异常，无从修复。
#
# ✅ 解法：预置 wheelhouse（见下），用 --find-links + --offline 彻底断网安装。
#    轮子在**宿主机**用清华源下好（实测 1.3 MB/s，约 90 秒下完 140 个包）。

WORKDIR /app/

# Place executables in the environment at the front of the path
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment
ENV PATH="/app/.venv/bin:$PATH"

# 🔑 app 包不 pip-install（见下方说明），靠 cwd 导入。
#    但 `python scripts/xxx.py` 的 sys.path[0] 是 scripts/ 而非 cwd，
#    `alembic upgrade head` 也可能不加 cwd —— 统一用 PYTHONPATH 兜底，
#    保证 alembic env.py 与 scripts/*.py 都能 `import app`。
ENV PYTHONPATH=/app/backend

# Install dependencies
#
# 🔴 为什么用 `uv pip install -r` 而不是 `uv sync --frozen`？
#    uv.lock 为每个包记录了 files.pythonhosted.org 的**完整直链**，
#    `uv sync --frozen` 会照这些 URL 逐个直取 —— `--find-links` 只参与
#    "解析"，不接管"按 URL 直取"，所以 wheelhouse 对 sync 无效（实测踩坑：
#    --offline 下报 "Network connectivity is disabled, but the requested
#    data wasn't found in the cache"）。
#
#    `uv pip install -r` 按 requirements 安装：清单里只有 包名+版本+hash，
#    没有 URL → uv 从 --find-links 的 wheelhouse 本地取 wheel 并校验 hash，
#    `--offline` 保证缺包时立刻报错而不是回落网络。
#
#    app 本身**不装包**：prestart.sh / CMD 都在 /app/backend 下以 cwd 导入 app/，
#    无需 pip 元数据（还省去离线构建 sdist 需要的 hatchling 依赖问题）。
#
#    wheelhouse / wheelhouse-req.txt 的生成与校验（宿主机，仓库根）→ scripts/wheelhouse.py：
#      python scripts/wheelhouse.py update   # 重新导出清单（已过滤 win32 包）+ 只补下缺失的 wheel
#      python scripts/wheelhouse.py check    # 校验清单与 uv.lock 一致、且 wheelhouse/ 内哈希匹配
#
#    ⚠️ 依赖一变（pyproject.toml / uv.lock）就必须重跑 update 再 build —— 忘掉的后果是
#       **静默缺件**：清单里没有那个新包，离线安装照样「成功」，应用启动后才 ImportError。
#       `check` 就是把这个静默故障变成显式报错（退出码非 0），提交前/构建前跑一次即可。
#
#    历史上手写这两条命令踩过的坑，都已固化进脚本（见其注释与常量）：
#      - `uv export` 必须带 `--no-emit-package app`：否则首行是 `-e ./backend`，pip 会报
#        "editable requirement ... cannot be installed when requiring hashes"
#      - 清单要删掉 win32 专属包块（colorama / pywin32 / tzdata）：pip 跨平台下载时按
#        **本机**环境评估标记，`sys_platform == 'win32'` 的行会直接报错
#      - 下载要**去掉环境标记**并显式给 `--platform manylinux*`：否则 linux-only 包
#        （faiss-cpu / pyarrow / uvloop / milvus-lite）会被 pip 按本机平台静默跳过
#      - jieba 在 PyPI 只有 sdist，下载它必须换 `--no-binary=:all:`
#      - 实测：142 个文件约 150MB，清华源 1-2 分钟下完（容器内同量要 30-60 分钟）。
RUN --mount=type=bind,source=wheelhouse,target=/app/wheelhouse \
    --mount=type=bind,source=wheelhouse-req.txt,target=/app/wheelhouse-req.txt \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python \
      -r /app/wheelhouse-req.txt \
      --find-links /app/wheelhouse \
      --offline \
      --no-cache \
      --compile-bytecode

COPY ./backend/scripts /app/backend/scripts

COPY ./backend/pyproject.toml ./backend/alembic.ini /app/backend/

COPY ./backend/app /app/backend/app

# 🔑 前端构建产物直接打进镜像（D1.3c）—— 分发时用户**无需自己构建前端**，
#    拉起镜像就有完整 webui。
#
#    路径必须与 compose.override.yml 的 `IrsBot_WEBUI_DIR=/app/frontend-dist` 一致；
#    本地开发时该目录被 `./frontend/dist:/app/frontend-dist` 绑定挂载覆盖，
#    所以改前端仍然"改完重新构建 dist 即生效"，不影响开发体验。
#
#    ⚠️ dist 不存在时本行会直接报错（COPY 的源必须存在）。
#    宿主机没有 bun，用 node 直接调 vite 构建：
#      cd frontend
#      node <仓库根>/node_modules/typescript/bin/tsc -p tsconfig.build.json
#      node <仓库根>/node_modules/vite/bin/vite.js build
COPY ./frontend/dist /app/frontend-dist

WORKDIR /app/backend/

CMD ["fastapi", "run", "--workers", "4", "app/main.py"]

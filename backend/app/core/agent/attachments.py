"""聊天附件基础设施 —— 落盘、解析、读取（Phase 16 / S1）。

设计要点：
- **目录按 用户/会话 两级隔离**：`{CHAT_ATTACHMENT_DIR}/{user_id}/{conversation_id}/`。
  删会话时直接 `rmtree` 该会话目录即可完成清理，不需要扫描消息表反查附件。
- **文件名只由服务端决定**：落盘名 `{att_id}_{原始名}`，其中 att_id 是服务端
  生成的 uuid4 hex。读取时**只按 att_id 在用户自己的会话目录内 glob**，
  客户端传来的文件名从不参与拼路径 → 结构上杜绝路径穿越。
- **不信任扩展名与 Content-Type**：图片按魔数嗅探真实类型；文档按扩展名
  路由解析器（解析器本身只支持四种格式，不在白名单内直接拒绝）。
- **超长文档截断而非报错**：截断是预期行为（模型上下文有限），
  但要如实回报 `truncated=True`，让前端能提示用户。
"""

import base64
import logging
import re
import shutil
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.knowledge_base.parsers import DocumentParser

logger = logging.getLogger(__name__)

#: 附件类型
KIND_DOCUMENT = "document"
KIND_IMAGE = "image"

#: 文档附件支持的扩展名（与解析器保持一致，单一真相源）
ALLOWED_DOC_EXTENSIONS: frozenset[str] = frozenset(
    DocumentParser.SUPPORTED_EXTENSIONS
)

#: 图片附件支持的 MIME（按魔数嗅探的产出，不接受客户端声明）
IMAGE_MIME_TYPES: frozenset[str] = frozenset({
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
})

#: att_id 必须是服务端生成的 32 位 hex——读取时凭它 glob，
#: 形状不对直接拒绝，不给任何拼路径的机会
_ATT_ID_RE = re.compile(r"^[0-9a-f]{32}$")

#: 单条消息最多携带的附件数：一次塞几十个文件既非真实场景，
#: 也会让送模型前逐个读盘解析变成拒绝服务入口。
MAX_PER_MESSAGE = 10


class AttachmentError(Exception):
    """附件处理失败（消息可直接展示给用户，属于预期内错误）。"""


def _root() -> Path:
    return Path(settings.CHAT_ATTACHMENT_DIR)


def attachment_dir(user_id: uuid.UUID | str, conversation_id: uuid.UUID | str) -> Path:
    """附件目录：`{root}/{user_id}/{conversation_id}/`。"""
    return _root() / str(user_id) / str(conversation_id)


def safe_filename(name: str | None) -> str:
    """剥掉客户端文件名里的目录成分与危险字符，只留展示用基名。

    落盘名还会再拼上服务端生成的 att_id，所以这里**不是唯一防线**；
    但仍然剥干净：原始名会入库并回显，带路径的名字没有意义且易误导。
    """
    base = Path(name or "").name
    # 只保留常见安全字符，其余压成下划线；全部被压掉时给个兜底名
    base = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", base).strip("._")
    return base[:120] or "unnamed"


def sniff_image_mime(data: bytes) -> str | None:
    """按魔数判断图片真实类型；不是已知图片则返回 None。

    为什么不信扩展名/Content-Type：二者都由客户端提供，改一个字节就能
    把 .exe 说成 .png。魔数要构造出合法头就真的得是那种图片。
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def read_document_text(path: Path) -> tuple[str, bool]:
    """解析文档为纯文本，超长按 ATTACHMENT_MAX_CHARS 截断。

    Returns:
        (文本, 是否被截断)
    """
    docs = await DocumentParser.parse(str(path))
    text = "\n\n".join(d.page_content for d in docs).strip()
    limit = settings.ATTACHMENT_MAX_CHARS
    if len(text) > limit:
        return text[:limit], True
    return text, False


def store(
    *,
    user_id: uuid.UUID | str,
    conversation_id: uuid.UUID | str,
    payload: bytes,
    filename: str | None,
) -> tuple[str, Path]:
    """把附件字节写入用户会话目录。

    不落 kind：文档/图片的判定属于消息元数据，随 Message.content 存库，
    磁盘上只需按 att_id 找到字节。

    Returns:
        (att_id, 落盘路径)
    """
    att_id = uuid.uuid4().hex
    dest_dir = attachment_dir(user_id, conversation_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{att_id}_{safe_filename(filename)}"
    dest.write_bytes(payload)
    return att_id, dest


def resolve(
    *,
    user_id: uuid.UUID | str,
    conversation_id: uuid.UUID | str,
    att_id: str,
) -> Path | None:
    """按 att_id 在**该用户该会话**的目录内定位附件文件。

    这是唯一的读取入口，也是路径穿越的最终防线：
    目录由服务端按 user_id + conversation_id 拼出（二者都来自已验证的上下文），
    文件名由 att_id 形状校验后 glob，客户端输入不参与路径拼接。
    """
    if not _ATT_ID_RE.match(att_id or ""):
        return None
    dest_dir = attachment_dir(user_id, conversation_id)
    if not dest_dir.is_dir():
        return None
    matches = sorted(dest_dir.glob(f"{att_id}_*"))
    # 目录内出现多个同 id 文件说明数据异常，宁可拒绝也不猜
    if len(matches) != 1:
        return None
    return matches[0]


def read_bytes(path: Path) -> bytes:
    """读取附件字节（送模型时用）。"""
    return path.read_bytes()


def describe(
    *,
    user_id: uuid.UUID | str,
    conversation_id: uuid.UUID | str,
    att_id: str,
) -> dict | None:
    """按 att_id 还原附件元数据（服务端权威，不信客户端任何声明）。

    WS 上行只带 att_id，kind/filename/size 一律从磁盘上的真实文件反推：
    客户端就算把 att_id 报成别的类型，也只会得到这里算出的真相。

    Returns:
        元数据 dict；att_id 无法定位时返回 None。
    """
    path = resolve(
        user_id=user_id, conversation_id=conversation_id, att_id=att_id
    )
    if path is None:
        return None
    # 落盘名是 `{att_id}_{safe_name}`，剥掉前缀即回原始展示名
    stored = path.name
    filename = stored[len(att_id) + 1 :] if stored.startswith(f"{att_id}_") else stored
    return {
        "id": att_id,
        "kind": KIND_DOCUMENT if is_allowed_document(filename) else KIND_IMAGE,
        "filename": filename,
        "size": path.stat().st_size,
    }


def extension_of(filename: str | None) -> str:
    """取小写扩展名（含点）。"""
    return Path(filename or "").suffix.lower()


def is_allowed_document(filename: str | None) -> bool:
    """文档扩展名是否在白名单内。"""
    return extension_of(filename) in ALLOWED_DOC_EXTENSIONS


async def build_document_context(
    meta: list[dict],
    *,
    user_id: uuid.UUID | str,
    conversation_id: uuid.UUID | str,
) -> str:
    """把文档附件解析成"随消息一起送模型"的文本块。

    文档正文**不进历史上下文**（只在本轮有效）。这里刻意不缓存解析结果：
    解析产物动辄上万字，存进消息表既撑大数据库，又会在历史回放时
    被反复重放——重解析一次是更小的代价。

    Returns:
        拼好的文本块；没有文档附件时返回空串。
    """
    blocks: list[str] = []
    for item in meta:
        if item.get("kind") != KIND_DOCUMENT:
            continue
        att_id = item.get("id")
        filename = item.get("filename") or "附件"
        path = resolve(
            user_id=user_id, conversation_id=conversation_id, att_id=str(att_id)
        )
        if path is None:
            blocks.append(f"【附件：{filename}】\n（文件已失效，无法读取）")
            continue
        try:
            text, truncated = await read_document_text(path)
        except Exception:
            logger.exception("附件读取失败: %s", filename)
            blocks.append(f"【附件：{filename}】\n（解析失败，无法读取内容）")
            continue
        suffix = "\n（内容过长已截断）" if truncated else ""
        blocks.append(f"【附件：{filename}】\n{text}{suffix}")
    return "\n\n".join(blocks)


def _image_data_url(
    item: dict, *, user_id: uuid.UUID | str, conversation_id: uuid.UUID | str
) -> str | None:
    """把一张图片附件读成 `data:<mime>;base64,<...>`，读不到返回 None。

    MIME 由**字节魔数**推定（不从客户端声明或扩展名取），与上传时的校验同源。
    """
    att_id = str(item.get("id") or "")
    path = resolve(user_id=user_id, conversation_id=conversation_id, att_id=att_id)
    if path is None:
        return None
    try:
        data = read_bytes(path)
    except OSError:
        logger.exception("图片附件读取失败: %s", item.get("filename"))
        return None
    mime = sniff_image_mime(data) or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


async def build_turn_content(
    text: str,
    meta: list[dict],
    *,
    user_id: uuid.UUID | str,
    conversation_id: uuid.UUID | str,
    supports_vision: bool,
) -> str | list[dict]:
    """把「本轮用户文本 + 附件」拼成送模型的 message content。

    - 文档：解析成文本块拼在后面（与模型是否支持视觉无关）
    - 图片：模型支持视觉 → 内联成 image_url 多模态块；不支持 → 走本地 OCR
      把图中文字提出来并入文本（OCR 不可用或没识别到文字时，退回一句中文提示）
    - 附件正文**不进历史**，只本轮有效（见 build_document_context）

    Returns:
        str（纯文本场景）或 LangChain 多模态 content 列表。
    """
    parts: list[str] = [text] if text else []
    doc_context = await build_document_context(
        meta, user_id=user_id, conversation_id=conversation_id
    )
    if doc_context:
        parts.append(doc_context)

    images = [m for m in meta if m.get("kind") == KIND_IMAGE]
    if not images:
        return "\n\n".join(parts)

    if supports_vision:
        blocks: list[dict] = [
            {"type": "text", "text": "\n\n".join(parts) or "（用户只发送了图片）"}
        ]
        for item in images:
            url = _image_data_url(
                item, user_id=user_id, conversation_id=conversation_id
            )
            if url is None:
                continue
            blocks.append({"type": "image_url", "image_url": {"url": url}})
        # 图片一张都没读出来：退回纯文本，别发一个只有文本块的「多模态」
        return blocks if len(blocks) > 1 else blocks[0]["text"]

    # ── 非视觉模型：本地 OCR 回退 ──
    # 延迟导入：ocr 依赖本模块的 resolve/KIND_IMAGE，顶层互相 import 会成环。
    from app.core.agent import ocr

    ocr_context = ""
    if settings.OCR_ENABLED:
        ocr_context = await ocr.build_image_context(
            meta, user_id=user_id, conversation_id=conversation_id
        )
    if ocr_context:
        parts.append(ocr_context)
        return "\n\n".join(parts)

    # OCR 也没能提供文字：如实说明原因，别让用户以为图片已被理解
    reason = (
        "本地 OCR 引擎不可用"
        if not settings.OCR_ENABLED or not ocr.is_available()
        else "本地 OCR 未识别到文字"
    )
    names = "、".join(str(m.get("filename") or "图片") for m in images)
    parts.append(f"（用户随消息发送了图片：{names}；当前模型不支持图片理解，且{reason}）")
    return "\n\n".join(parts)


def remove_conversation_dir(
    user_id: uuid.UUID | str, conversation_id: uuid.UUID | str
) -> None:
    """删除会话的全部附件（随会话删除而删）。

    清理失败绝不能影响删会话本身，整段吞异常仅留日志。
    """
    dest_dir = attachment_dir(user_id, conversation_id)
    try:
        shutil.rmtree(dest_dir, ignore_errors=True)
    except Exception:
        logger.exception("附件目录清理失败: %s", dest_dir)

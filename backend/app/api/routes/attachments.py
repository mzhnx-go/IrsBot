"""聊天附件上传路由（Phase 16 / S1）。

上行只有这一个端点；附件字节**不走 WebSocket**——WS 只带 att_id，
字节由后端在送模型时自己从磁盘读。这样避免把 WS 帧撑爆，
也让"谁有权读这个文件"只剩一处需要守卫。

归属校验分两层：
1. 会话必须是当前用户的（复用 ConversationManager.get_conversation）；
2. 附件读取只在该用户该会话的目录内按 att_id 定位（见 core/agent/attachments）。
"""

import logging
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.core.agent import attachments
from app.core.agent.conversation import ConversationManager
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

#: 分块读取的大小：一边读一边计数，超限立刻中断，
#: 避免把超大文件整个读进内存再判断（那就是给自己造 OOM）
_CHUNK = 1024 * 1024


class AttachmentOut(BaseModel):
    """上传成功后的附件元数据（前端据此渲染 chip / 缩略图）。"""

    id: str
    kind: str
    filename: str
    size: int
    mime: str | None = None
    #: 文档解析出的字符数（图片为 None）
    extracted_chars: int | None = None
    #: 文档是否因超长被截断
    truncated: bool = False


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    """读满 limit 就抛错，绝不把超大文件读全。"""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=400,
                detail=f"文件超过大小上限（{limit // 1024 // 1024}MB）",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    session: SessionDep,
    current_user: CurrentUser,
    conversation_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
):
    """上传一个聊天附件（文档或图片）。

    文档：校验扩展名 → 落盘 → 解析为文本并按上限截断（解析失败即删文件报错）。
    图片：嗅探魔数确认是真实图片 → 落盘（不做任何解析）。
    """
    # 会话归属校验：附件目录按 用户/会话 组织，会话不属于当前用户就没资格写
    conv_manager = ConversationManager(session)
    conversation = conv_manager.get_conversation(conversation_id, current_user.id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="对话不存在")

    filename = attachments.safe_filename(file.filename)

    if attachments.is_allowed_document(filename):
        limit = settings.ATTACHMENT_MAX_DOC_BYTES
        payload = await _read_capped(file, limit)
        att_id, dest = attachments.store(
            user_id=current_user.id,
            conversation_id=conversation_id,
            payload=payload,
            filename=filename,
        )
        try:
            text, truncated = await attachments.read_document_text(dest)
        except Exception:
            # 解析失败就把刚落的文件删掉：留着一个永远用不上的孤儿文件，
            # 只会让"附件目录为什么越来越大"变成无解题
            dest.unlink(missing_ok=True)
            logger.exception("附件解析失败: %s", filename)
            raise HTTPException(
                status_code=400,
                detail="文档解析失败，请确认文件未损坏且格式受支持",
            )
        return AttachmentOut(
            id=att_id,
            kind=attachments.KIND_DOCUMENT,
            filename=filename,
            size=len(payload),
            extracted_chars=len(text),
            truncated=truncated,
        )

    # 走到这里按图片处理：先嗅探魔数，不是已知图片类型就明确拒绝。
    # 注意顺序——扩展名不在文档白名单时也可能是个未知格式，统一报"不支持"。
    payload = await _read_capped(file, settings.ATTACHMENT_MAX_IMAGE_BYTES)
    mime = attachments.sniff_image_mime(payload)
    if mime is None:
        allowed = "、".join(sorted(attachments.ALLOWED_DOC_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式，仅支持 {allowed} 与 PNG/JPEG/GIF/WebP 图片",
        )
    att_id, _ = attachments.store(
        user_id=current_user.id,
        conversation_id=conversation_id,
        payload=payload,
        filename=filename,
    )
    return AttachmentOut(
        id=att_id,
        kind=attachments.KIND_IMAGE,
        filename=filename,
        size=len(payload),
        mime=mime,
    )

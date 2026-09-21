"""语音能力路由（P9b STT / P9c TTS）。

两条端点都是「薄转发」：本模块只负责鉴权、限长、把上游错误翻成中文，
真正的上游协议在 `core/agent/audio.py`。凭据固定取当前用户
`capability="stt"` / `"tts"` 的默认源——**没有跨租户回退**，
没配就是 400，不会去用别人的 Key。
"""

import logging

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.core.agent import audio
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

#: 分块读取大小：边读边计数，超限立刻中断（同附件上传，避免先读满内存再判断）
_CHUNK = 1024 * 1024

#: 录音文件统一的落点扩展名（MediaRecorder 出来的多是 webm/ogg，统一按 webm 命名，
#: 上游普遍按内容嗅探而非扩展名）
_DEFAULT_FILENAME = "recording.webm"


class TranscriptionOut(BaseModel):
    """识别结果（前端把它填进输入框，用户确认后再发送）。"""

    text: str


class SpeechIn(BaseModel):
    """合成请求：text 必填，voice 不传则用上游默认音色。"""

    text: str
    voice: str | None = None


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    """读满 limit 就抛错，绝不把超大音频读全。"""
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
                detail=f"录音超过大小上限（{limit // 1024 // 1024}MB）",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _endpoint_or_400(session, user, capability: str) -> audio.AudioEndpoint:
    try:
        return audio.resolve_audio_endpoint(session, user.id, capability)
    except audio.AudioSourceError as exc:
        # 配置问题不是服务端故障：400 + 可执行的中文指引
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/audio/transcriptions", response_model=TranscriptionOut)
async def transcribe_audio(
    session: SessionDep,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    language: str | None = Form(None),
):
    """语音转文字：上传一段录音，返回识别文本。"""
    endpoint = _endpoint_or_400(session, current_user, "stt")
    payload = await _read_capped(file, settings.AUDIO_MAX_BYTES)
    if not payload:
        raise HTTPException(status_code=400, detail="录音内容为空")
    try:
        text = await audio.transcribe(
            endpoint,
            data=payload,
            filename=file.filename or _DEFAULT_FILENAME,
            content_type=file.content_type,
            language=language,
        )
    except audio.AudioUpstreamError as exc:
        logger.warning("语音识别上游失败: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TranscriptionOut(text=text)


@router.post("/audio/speech")
async def synthesize_speech(
    session: SessionDep,
    current_user: CurrentUser,
    body: SpeechIn,
):
    """文字转语音：返回整段音频字节（不做流式，前端直接播放）。"""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="文本为空，无法合成语音")
    if len(text) > settings.AUDIO_TTS_MAX_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"文本过长（上限 {settings.AUDIO_TTS_MAX_CHARS} 字），请分段朗读",
        )
    endpoint = _endpoint_or_400(session, current_user, "tts")
    try:
        data, media_type = await audio.synthesize(
            endpoint, text=text, voice=body.voice
        )
    except audio.AudioUpstreamError as exc:
        logger.warning("语音合成上游失败: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=data, media_type=media_type)

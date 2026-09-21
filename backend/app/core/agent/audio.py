"""P9b/P9c：语音转文字（STT）与文字转语音（TTS）的上游调用。

凭据来源只有一处：用户在「模型源」页配置的 `capability="stt"` / `"tts"`
默认源（P5 能力维度）。**没有 .env 回落**——这两类能力此前完全没有实现，
不存在需要兼容的存量配置；没配就报一个明确的中文错误，而不是静默抓一个源
（用户会以为"点了没反应"，比拿到错误更难排查）。

上游协议按 OpenAI 兼容的 `/audio/transcriptions`（multipart）与
`/audio/speech`（JSON → 音频字节）。anthropic / gemini 没有对应的音频端点，
因此这两类源在此被明确拒绝，不装作能用。

超时/代理等「高级配置」暂未接入（与 provider_models 的拉清单不同，那是
可选辅助功能；这里是主链路，接错比不接更糟，先只走 base_url + Key）。
"""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

#: openai 类型源没填 base_url 时的默认网关（与 provider_models 一致）
DEFAULT_BASE_URL = "https://api.openai.com/v1"

_DEFAULT_TIMEOUT = 120.0

#: 上游错误响应里回显给用户的最大字符数（避免把整页 HTML 塞进 detail）
_MAX_DETAIL = 300


class AudioSourceError(RuntimeError):
    """配置层面不可用（没配源 / 源类型不支持音频）。

    message 是给用户看的中文，路由层直接转成 400。
    """


class AudioUpstreamError(RuntimeError):
    """上游调用失败（连接错误 / 非 2xx / 响应形状不对），路由层转成 502。"""


@dataclass(frozen=True)
class AudioEndpoint:
    """一次音频调用所需的凭据与地址（已解密，只在本模块内传递）。"""

    api_key: str
    base_url: str
    model: str


def resolve_audio_endpoint(session, user_id, capability: str) -> AudioEndpoint:
    """取该用户 `capability` 维度的默认源，作为音频上游。

    Args:
        session: 数据库会话。
        user_id: 归属用户；为 None 时必定拿不到源（fail closed）。
        capability: "stt" 或 "tts"。

    Raises:
        AudioSourceError: 没配默认源，或配的是非 openai 类型。
    """
    # 惰性导入：provider.py 已 import 不少东西，避免模块级循环引用
    from app.core.agent.provider import ProviderManager

    mgr = ProviderManager(session)
    pc = mgr.get_active_config(user_id=user_id, capability=capability)
    if pc is None:
        raise AudioSourceError(
            f"尚未配置{_capability_label(capability)}模型源，请先到「模型源」页添加并设为默认"
        )
    if pc.provider_type.lower() != "openai":
        raise AudioSourceError(
            f"{_capability_label(capability)}仅支持 openai 兼容协议的服务商"
            f"（当前为 {pc.provider_type}）"
        )
    api_key, _ = mgr.resolve_api_key(pc)
    return AudioEndpoint(
        api_key=api_key,
        base_url=(pc.base_url or DEFAULT_BASE_URL).rstrip("/"),
        model=pc.model_name,
    )


def _capability_label(capability: str) -> str:
    return "语音转文字" if capability == "stt" else "文字转语音"


def _upstream_detail(resp: httpx.Response) -> str:
    """从上游错误响应里尽量抠出一句可读的原因。"""
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:_MAX_DETAIL]
        if isinstance(err, str):
            return err[:_MAX_DETAIL]
        if payload.get("message"):
            return str(payload["message"])[:_MAX_DETAIL]
    return (resp.text or "").strip()[:_MAX_DETAIL] or f"HTTP {resp.status_code}"


async def transcribe(
    endpoint: AudioEndpoint,
    *,
    data: bytes,
    filename: str,
    content_type: str | None = None,
    language: str | None = None,
) -> str:
    """把音频字节发给上游做语音识别，返回识别文本。

    Raises:
        AudioUpstreamError: 网络失败 / 上游非 2xx / 响应里没有 text。
    """
    files = {"file": (filename, data, content_type or "application/octet-stream")}
    form: dict[str, str] = {"model": endpoint.model}
    if language:
        form["language"] = language

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{endpoint.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {endpoint.api_key}"},
                files=files,
                data=form,
            )
    except httpx.HTTPError as exc:
        raise AudioUpstreamError(f"语音识别请求失败：{exc}") from exc

    if resp.status_code >= 400:
        raise AudioUpstreamError(f"语音识别失败：{_upstream_detail(resp)}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise AudioUpstreamError("语音识别上游返回了非 JSON 响应") from exc
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str):
        raise AudioUpstreamError("语音识别上游响应缺少 text 字段")
    return text


async def synthesize(
    endpoint: AudioEndpoint,
    *,
    text: str,
    voice: str | None = None,
    response_format: str = "mp3",
) -> tuple[bytes, str]:
    """把文本发给上游合成语音，返回 (音频字节, media type)。

    Raises:
        AudioUpstreamError: 网络失败 / 上游非 2xx / 上游返回了空音频。
    """
    body: dict[str, str] = {
        "model": endpoint.model,
        "input": text,
        "response_format": response_format,
    }
    if voice:
        body["voice"] = voice

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{endpoint.base_url}/audio/speech",
                headers={"Authorization": f"Bearer {endpoint.api_key}"},
                json=body,
            )
    except httpx.HTTPError as exc:
        raise AudioUpstreamError(f"语音合成请求失败：{exc}") from exc

    if resp.status_code >= 400:
        raise AudioUpstreamError(f"语音合成失败：{_upstream_detail(resp)}")

    audio_bytes = resp.content
    if not audio_bytes:
        raise AudioUpstreamError("语音合成上游返回了空音频")
    media_type = resp.headers.get("content-type") or _media_type(response_format)
    return audio_bytes, media_type


def _media_type(response_format: str) -> str:
    return {
        "mp3": "audio/mpeg",
        "opus": "audio/ogg",
        "wav": "audio/wav",
        "aac": "audio/aac",
        "flac": "audio/flac",
    }.get(response_format, "audio/mpeg")

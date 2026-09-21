"""P9b/P9c 音频能力单元测试（上游适配 + 凭据解析）。

不打网：httpx.AsyncClient 被换成 MockTransport（与 test_provider_models 同款做法）。
凭据解析走真实 ProviderConfig 表——「按能力取默认源」是这个模块的核心不变量，
用假对象测就测不到它。
"""

import uuid

import httpx
import pytest
from sqlmodel import Session, select

from app.core.agent import audio
from app.core.agent.provider import ProviderManager
from app.core.config import settings
from app.core.db.models import ProviderConfig
from app.core.db.sqlmodel_models import User

_REAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def cleanup_audio_providers(db: Session):
    """本文件建的源用完即删：默认源的唯一索引是全局的，留着会影响别的用例。"""
    yield

    def _drop(capability: str) -> None:
        rows = db.exec(
            select(ProviderConfig).where(
                ProviderConfig.capability == capability,
                ProviderConfig.name.like("test-audio-%"),
            )
        ).all()
        for row in rows:
            db.delete(row)

    for cap in ("stt", "tts", "chat"):
        _drop(cap)
    db.commit()


@pytest.fixture
def owner_id(db: Session) -> uuid.UUID:
    """取库里真实的超管 id（有真实 User 行，不需要绕外键）。"""
    return db.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).one().id


def _make_source(
    db: Session,
    owner_id: uuid.UUID,
    *,
    capability: str,
    model_name: str = "whisper-1",
    provider_type: str = "openai",
    base_url: str | None = "https://api.example.com/v1",
    is_default: bool = True,
) -> ProviderConfig:
    mgr = ProviderManager(db)
    return mgr.create_provider(
        user_id=owner_id,
        name=f"test-audio-{uuid.uuid4().hex[:8]}",
        provider_type=provider_type,
        api_key="sk-audio-test",
        model_name=model_name,
        capability=capability,
        base_url=base_url,
        is_default=is_default,
    )


def _patch_async_client(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """把 audio 模块里的 httpx.AsyncClient 指向 MockTransport。

    原类必须在模块级捕获一次，否则重复 patch 会形成嵌套包装。
    """

    def factory(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(audio.httpx, "AsyncClient", factory)


# ── 凭据解析 ──────────────────────────────────────────────────


class TestResolveAudioEndpoint:
    def test_missing_source_raises(self, db: Session, owner_id: uuid.UUID):
        """没配 stt 源 → 明确的 AudioSourceError（不是静默抓一个源）。"""
        with pytest.raises(audio.AudioSourceError, match="尚未配置语音转文字模型源"):
            audio.resolve_audio_endpoint(db, owner_id, "stt")

    def test_reads_default_source(self, db: Session, owner_id: uuid.UUID):
        """配上默认源后，Key / base_url / 模型名原样带出。"""
        _make_source(
            db, owner_id, capability="stt", model_name="FunAudioLLM/SenseVoiceSmall"
        )
        ep = audio.resolve_audio_endpoint(db, owner_id, "stt")
        assert ep.model == "FunAudioLLM/SenseVoiceSmall"
        assert ep.base_url == "https://api.example.com/v1"
        assert ep.api_key == "sk-audio-test"  # 解密后的明文

    def test_capability_isolation(self, db: Session, owner_id: uuid.UUID):
        """只有 tts 源时取 stt 必须报错——不能把朗读源当识别源。"""
        _make_source(db, owner_id, capability="tts", model_name="tts-1")
        with pytest.raises(audio.AudioSourceError, match="语音转文字"):
            audio.resolve_audio_endpoint(db, owner_id, "stt")
        assert audio.resolve_audio_endpoint(db, owner_id, "tts").model == "tts-1"

    def test_non_openai_type_rejected(self, db: Session, owner_id: uuid.UUID):
        """anthropic 没有音频端点：明确拒绝，不装作能用。"""
        _make_source(db, owner_id, capability="stt", provider_type="anthropic")
        with pytest.raises(audio.AudioSourceError, match="仅支持 openai 兼容"):
            audio.resolve_audio_endpoint(db, owner_id, "stt")

    def test_none_user_gets_nothing(self, db: Session):
        """user_id=None fail closed，绝不回落到「全库任意默认源」。"""
        with pytest.raises(audio.AudioSourceError):
            audio.resolve_audio_endpoint(db, None, "stt")

    def test_blank_base_url_falls_back_to_openai(
        self, db: Session, owner_id: uuid.UUID
    ):
        """没填 base_url 时用 openai 官方网关（与 provider_models 一致）。"""
        _make_source(db, owner_id, capability="stt", base_url=None)
        assert (
            audio.resolve_audio_endpoint(db, owner_id, "stt").base_url
            == audio.DEFAULT_BASE_URL
        )

    def test_trailing_slash_stripped(self, db: Session, owner_id: uuid.UUID):
        """base_url 带尾斜杠不能拼出 `//audio/...`。"""
        _make_source(db, owner_id, capability="stt", base_url="https://x.com/v1/")
        assert audio.resolve_audio_endpoint(db, owner_id, "stt").base_url == (
            "https://x.com/v1"
        )


# ── 语音识别（STT）───────────────────────────────────────────


class TestTranscribe:
    @pytest.mark.asyncio
    async def test_posts_multipart_and_returns_text(self, monkeypatch):
        """请求形状：multipart 带 file + model，Bearer 鉴权，解析 text。"""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = request.content.decode("utf-8", "replace")
            return httpx.Response(200, json={"text": "你好，世界"}, request=request)

        _patch_async_client(monkeypatch, handler)
        text = await audio.transcribe(
            audio.AudioEndpoint("sk-x", "https://api.example.com/v1", "whisper-1"),
            data=b"fake-bytes",
            filename="recording.webm",
            content_type="audio/webm",
        )
        assert text == "你好，世界"
        assert seen["url"] == "https://api.example.com/v1/audio/transcriptions"
        assert seen["auth"] == "Bearer sk-x"
        assert "whisper-1" in seen["body"]
        assert "recording.webm" in seen["body"]

    @pytest.mark.asyncio
    async def test_language_is_forwarded_when_given(self, monkeypatch):
        """传了 language 就带上（不传则不带，别塞空值）。"""
        bodies: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(request.content.decode("utf-8", "replace"))
            return httpx.Response(200, json={"text": "ok"}, request=request)

        _patch_async_client(monkeypatch, handler)
        ep = audio.AudioEndpoint("sk-x", "https://api.example.com/v1", "whisper-1")
        await audio.transcribe(
            ep, data=b"x", filename="a.webm", content_type=None, language="zh"
        )
        await audio.transcribe(ep, data=b"x", filename="a.webm", content_type=None)

        assert 'name="language"' in bodies[0] and "zh" in bodies[0]
        assert 'name="language"' not in bodies[1]

    @pytest.mark.asyncio
    async def test_network_error_becomes_upstream_error(self, monkeypatch):
        """连接失败包成 AudioUpstreamError（路由层翻成 502），不是裸 httpx 异常。"""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        _patch_async_client(monkeypatch, handler)
        with pytest.raises(audio.AudioUpstreamError, match="语音识别请求失败"):
            await audio.transcribe(
                audio.AudioEndpoint("sk-x", "https://x/v1", "whisper-1"),
                data=b"x",
                filename="a.webm",
            )

    @pytest.mark.asyncio
    async def test_upstream_4xx_surfaces_reason(self, monkeypatch):
        """上游 4xx：把 error.message 抠出来给用户看，而不是只报状态码。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={"error": {"message": "Invalid API key"}},
                request=request,
            )

        _patch_async_client(monkeypatch, handler)
        with pytest.raises(audio.AudioUpstreamError, match="Invalid API key"):
            await audio.transcribe(
                audio.AudioEndpoint("sk-x", "https://x/v1", "whisper-1"),
                data=b"x",
                filename="a.webm",
            )

    @pytest.mark.asyncio
    async def test_non_json_response_rejected(self, monkeypatch):
        """上游返回 HTML（网关错误页）时给明确提示，不抛 JSONDecodeError。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=b"<html>oops</html>", request=request
            )

        _patch_async_client(monkeypatch, handler)
        with pytest.raises(audio.AudioUpstreamError, match="非 JSON 响应"):
            await audio.transcribe(
                audio.AudioEndpoint("sk-x", "https://x/v1", "whisper-1"),
                data=b"x",
                filename="a.webm",
            )

    @pytest.mark.asyncio
    async def test_missing_text_field_rejected(self, monkeypatch):
        """响应是 JSON 但没有 text（形状不符）要报错，不能返回 None。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"result": "x"}, request=request)

        _patch_async_client(monkeypatch, handler)
        with pytest.raises(audio.AudioUpstreamError, match="缺少 text"):
            await audio.transcribe(
                audio.AudioEndpoint("sk-x", "https://x/v1", "whisper-1"),
                data=b"x",
                filename="a.webm",
            )


# ── 语音合成（TTS）────────────────────────────────────────────


class TestSynthesize:
    @pytest.mark.asyncio
    async def test_posts_json_and_returns_audio(self, monkeypatch):
        """请求形状：JSON 带 model/input/response_format；返回字节 + media type。"""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = request.content.decode()
            return httpx.Response(
                200,
                content=b"ID3-fake-mp3",
                headers={"content-type": "audio/mpeg"},
                request=request,
            )

        _patch_async_client(monkeypatch, handler)
        data, media = await audio.synthesize(
            audio.AudioEndpoint("sk-x", "https://x/v1", "tts-1"), text="你好"
        )
        assert data == b"ID3-fake-mp3"
        assert media == "audio/mpeg"
        assert seen["url"] == "https://x/v1/audio/speech"
        assert "tts-1" in seen["body"] and "你好" in seen["body"]
        assert '"response_format":"mp3"' in seen["body"].replace(" ", "")

    @pytest.mark.asyncio
    async def test_voice_forwarded_only_when_given(self, monkeypatch):
        """voice 传了才带（上游默认音色靠不传生效）。"""
        bodies: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(request.content.decode())
            return httpx.Response(200, content=b"a", request=request)

        _patch_async_client(monkeypatch, handler)
        ep = audio.AudioEndpoint("sk-x", "https://x/v1", "tts-1")
        await audio.synthesize(ep, text="hi", voice="alloy")
        await audio.synthesize(ep, text="hi")

        assert "alloy" in bodies[0]
        assert "voice" not in bodies[1]

    @pytest.mark.asyncio
    async def test_empty_audio_rejected(self, monkeypatch):
        """200 但零字节：当失败处理（前端拿到空 blob 只会静默播不出声）。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"", request=request)

        _patch_async_client(monkeypatch, handler)
        with pytest.raises(audio.AudioUpstreamError, match="空音频"):
            await audio.synthesize(
                audio.AudioEndpoint("sk-x", "https://x/v1", "tts-1"), text="hi"
            )

    @pytest.mark.asyncio
    async def test_network_error_becomes_upstream_error(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        _patch_async_client(monkeypatch, handler)
        with pytest.raises(audio.AudioUpstreamError, match="语音合成请求失败"):
            await audio.synthesize(
                audio.AudioEndpoint("sk-x", "https://x/v1", "tts-1"), text="hi"
            )

    @pytest.mark.asyncio
    async def test_missing_content_type_falls_back(self, monkeypatch):
        """上游不带 content-type 时按请求格式推断（mp3 → audio/mpeg）。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"audio", request=request)

        _patch_async_client(monkeypatch, handler)
        _, media = await audio.synthesize(
            audio.AudioEndpoint("sk-x", "https://x/v1", "tts-1"), text="hi"
        )
        assert media == "audio/mpeg"

    @pytest.mark.asyncio
    async def test_wav_format_media_type(self, monkeypatch):
        """response_format 换成 wav 时 media type 跟着变。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"RIFF", request=request)

        _patch_async_client(monkeypatch, handler)
        _, media = await audio.synthesize(
            audio.AudioEndpoint("sk-x", "https://x/v1", "tts-1"),
            text="hi",
            response_format="wav",
        )
        assert media == "audio/wav"


def test_upstream_detail_falls_back_to_status():
    """上游返回非 JSON、非空文本时回落成 HTTP 状态码描述。"""
    req = httpx.Request("POST", "https://x/v1/audio/speech")
    assert audio._upstream_detail(
        httpx.Response(500, content=b"", request=req)
    ) == "HTTP 500"
    assert (
        audio._upstream_detail(httpx.Response(500, text="boom", request=req))
        == "boom"
    )


def test_upstream_detail_understands_fastapi_style_detail():
    """兼容网关回 {"detail": ...} 时也要抠出原因（实机 A/B 撞到过）。

    真实场景：把 base_url 指向一个 FastAPI 写的网关（如 LiteLLM）的
    非音频路径，上游回的就是 {"detail":"Not Found"}；只认 error.message
    会把整段 JSON 当文案展示给用户。
    """
    req = httpx.Request("POST", "https://x/v1/audio/transcriptions")
    assert (
        audio._upstream_detail(
            httpx.Response(404, json={"detail": "Not Found"}, request=req)
        )
        == "Not Found"
    )

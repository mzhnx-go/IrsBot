"""语音端点测试（P9b STT / P9c TTS 的路由层）。

上游一律用 MockTransport 假掉，不真连网；凭据走真实 ProviderConfig 表
（「按 capability 取默认源、取不到就 400 且不跨租户」是这两个端点的红线）。
"""

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.agent import audio
from app.core.config import settings
from app.core.db.models import ProviderConfig
from tests.api.routes.test_providers import _NAME_PREFIX, _create_provider

STT_URL = f"{settings.API_V1_STR}/agent/audio/transcriptions"
TTS_URL = f"{settings.API_V1_STR}/agent/audio/speech"

_REAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def cleanup_audio_sources(db: Session):
    """前后都清：默认源的唯一索引是全局的，stt/tts 的残留会让别的用例假绿/假红。"""

    def _drop() -> None:
        rows = db.exec(
            select(ProviderConfig).where(
                ProviderConfig.name.like(f"{_NAME_PREFIX}%"),
                ProviderConfig.capability.in_(("stt", "tts")),  # type: ignore[attr-defined]
            )
        ).all()
        for row in rows:
            db.delete(row)
        db.commit()

    _drop()
    yield
    _drop()


def _patch_async_client(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    def factory(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(audio.httpx, "AsyncClient", factory)


def _seed_source(
    client: TestClient, headers: dict, capability: str, **overrides
) -> dict:
    return _create_provider(
        client,
        headers,
        capability=capability,
        is_default=True,
        model_name="whisper-1" if capability == "stt" else "tts-1",
        **overrides,
    )


def _post_recording(client: TestClient, headers: dict | None, payload=b"audio"):
    return client.post(
        STT_URL,
        headers=headers or {},
        files={"file": ("rec.webm", payload, "audio/webm")},
    )


def _fake_transcription(text: str = "识别结果"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": text}, request=request)

    return handler


# ── 鉴权 ──────────────────────────────────────────────────────


def test_transcription_requires_token(client: TestClient) -> None:
    assert _post_recording(client, None).status_code == 401


def test_speech_requires_token(client: TestClient) -> None:
    assert client.post(TTS_URL, json={"text": "hi"}).status_code == 401


# ── STT ───────────────────────────────────────────────────────


def test_transcription_returns_text(
    client: TestClient, superuser_token_headers: dict, monkeypatch
) -> None:
    """配好 stt 源后：上传录音 → 上游 text 原样返回。"""
    _seed_source(client, superuser_token_headers, "stt")
    _patch_async_client(monkeypatch, _fake_transcription("今天天气不错"))

    res = _post_recording(client, superuser_token_headers)

    assert res.status_code == 200, res.text
    assert res.json() == {"text": "今天天气不错"}


def test_transcription_without_source_is_400(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """没配 stt 源 → 400 且给出可执行的中文指引（不是 500、不是静默抓源）。"""
    res = _post_recording(client, superuser_token_headers)
    assert res.status_code == 400
    assert res.json()["detail"] == (
        "尚未配置语音转文字模型源，请先到「模型源」页添加并设为默认"
    )


def test_transcription_rejects_non_openai_source(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """anthropic 源没有音频端点：明确拒绝，不做「假装支持」。"""
    _seed_source(
        client, superuser_token_headers, "stt", provider_type="anthropic"
    )
    res = _post_recording(client, superuser_token_headers)
    assert res.status_code == 400
    assert "仅支持 openai 兼容" in res.json()["detail"]


def test_transcription_empty_body_is_400(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """零字节录音：直接拒，不浪费一次上游调用。"""
    _seed_source(client, superuser_token_headers, "stt")
    res = _post_recording(client, superuser_token_headers, payload=b"")
    assert res.status_code == 400
    assert res.json()["detail"] == "录音内容为空"


def test_transcription_oversize_is_400(
    client: TestClient, superuser_token_headers: dict, monkeypatch
) -> None:
    """超过 AUDIO_MAX_BYTES 就在读的时候中断（不是先读满内存再判断）。"""
    _seed_source(client, superuser_token_headers, "stt")
    monkeypatch.setattr(settings, "AUDIO_MAX_BYTES", 8)

    res = _post_recording(client, superuser_token_headers, payload=b"x" * 64)

    assert res.status_code == 400
    assert "上限" in res.json()["detail"]


def test_transcription_upstream_failure_is_502(
    client: TestClient, superuser_token_headers: dict, monkeypatch
) -> None:
    """上游非 2xx → 502 且回显上游原因（用户要能看出是 Key 还是网络）。"""
    _seed_source(client, superuser_token_headers, "stt")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "Invalid API key"}}, request=request
        )

    _patch_async_client(monkeypatch, handler)
    res = _post_recording(client, superuser_token_headers)

    assert res.status_code == 502
    assert "Invalid API key" in res.json()["detail"]


def test_transcription_does_not_leak_other_users_source(
    client: TestClient,
    superuser_token_headers: dict,
    normal_user_token_headers: dict,
) -> None:
    """别的用户配了 stt 源，我这边依然是没有源（400）——不跨租户取凭据。"""
    _seed_source(client, normal_user_token_headers, "stt")
    res = _post_recording(client, superuser_token_headers)
    assert res.status_code == 400


# ── TTS ───────────────────────────────────────────────────────


def test_speech_returns_audio_bytes(
    client: TestClient, superuser_token_headers: dict, monkeypatch
) -> None:
    """配好 tts 源后：合成结果按上游 media type 原样回吐。"""
    _seed_source(client, superuser_token_headers, "tts")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"ID3-mp3-bytes",
            headers={"content-type": "audio/mpeg"},
            request=request,
        )

    _patch_async_client(monkeypatch, handler)
    res = client.post(
        TTS_URL, headers=superuser_token_headers, json={"text": "你好"}
    )

    assert res.status_code == 200, res.text
    assert res.content == b"ID3-mp3-bytes"
    assert res.headers["content-type"].startswith("audio/mpeg")


def test_speech_without_source_is_400(
    client: TestClient, superuser_token_headers: dict
) -> None:
    res = client.post(
        TTS_URL, headers=superuser_token_headers, json={"text": "你好"}
    )
    assert res.status_code == 400
    assert res.json()["detail"] == (
        "尚未配置文字转语音模型源，请先到「模型源」页添加并设为默认"
    )


def test_speech_blank_text_is_400(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """空白文本：连源都不用解析就该拒（先校验后取凭据）。"""
    res = client.post(
        TTS_URL, headers=superuser_token_headers, json={"text": "   "}
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "文本为空，无法合成语音"


def test_speech_too_long_is_400(
    client: TestClient, superuser_token_headers: dict, monkeypatch
) -> None:
    """超过 AUDIO_TTS_MAX_CHARS：明确拒绝，不把整篇文档念出去。"""
    monkeypatch.setattr(settings, "AUDIO_TTS_MAX_CHARS", 5)
    res = client.post(
        TTS_URL, headers=superuser_token_headers, json={"text": "一二三四五六"}
    )
    assert res.status_code == 400
    assert "文本过长" in res.json()["detail"]


def test_speech_upstream_failure_is_502(
    client: TestClient, superuser_token_headers: dict, monkeypatch
) -> None:
    _seed_source(client, superuser_token_headers, "tts")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    _patch_async_client(monkeypatch, handler)
    res = client.post(
        TTS_URL, headers=superuser_token_headers, json={"text": "你好"}
    )
    assert res.status_code == 502
    assert "语音合成请求失败" in res.json()["detail"]


def test_speech_uses_own_capability_source(
    client: TestClient, superuser_token_headers: dict, monkeypatch
) -> None:
    """stt 源不能被 tts 借用：只有 stt 时请求朗读必须 400。"""
    _seed_source(client, superuser_token_headers, "stt")
    res = client.post(
        TTS_URL, headers=superuser_token_headers, json={"text": "你好"}
    )
    assert res.status_code == 400
    assert "文字转语音" in res.json()["detail"]


def test_one_default_per_capability_coexists(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """stt 与 tts 各一条默认源可以共存（P5 索引不能误伤这两类）。"""
    stt = _seed_source(client, superuser_token_headers, "stt")
    tts = _seed_source(client, superuser_token_headers, "tts")
    assert stt["is_default"] is True and tts["is_default"] is True

    rows = client.get(
        f"{settings.API_V1_STR}/providers",
        headers=superuser_token_headers,
        params={"capability": "tts"},
    )
    assert rows.status_code == 200
    assert [r["id"] for r in rows.json()] == [tts["id"]]

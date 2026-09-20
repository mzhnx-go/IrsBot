"""本地 OCR 回退单测（Phase 16 / S6）。

只测本模块的逻辑，不依赖 rapidocr 真的装上：
- 引擎不可用时一律返回空串（上层据此退回文字提示）
- 图片定位沿用 attachments.resolve（越权/失效都由它挡住）
- 识别结果拼块与超长截断

真引擎的端到端验证走容器验收（镜像里才有 onnxruntime + 系统库），
这里用 monkeypatch 把 `recognize` 换掉，保证单测在任意机器上可复现。
"""

import uuid
from pathlib import Path

import pytest

from app.core.agent import attachments, ocr
from app.core.config import settings

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def attach_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHAT_ATTACHMENT_DIR", str(tmp_path))


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _store_image(user_id, conv_id, filename: str = "图.png") -> dict:
    att_id, _ = attachments.store(
        user_id=user_id,
        conversation_id=conv_id,
        payload=PNG,
        filename=filename,
    )
    return {
        "id": att_id,
        "kind": attachments.KIND_IMAGE,
        "filename": filename,
        "size": len(PNG),
    }


# ── is_available ───────────────────────────────────────────


def test_is_available_follows_find_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr.importlib.util, "find_spec", lambda name: None)
    assert ocr.is_available() is False
    monkeypatch.setattr(ocr.importlib.util, "find_spec", lambda name: object())
    assert ocr.is_available() is True


# ── build_image_context ────────────────────────────────────


async def test_no_images_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _explode(*_a, **_k):
        raise AssertionError("没有图片时不该碰引擎")

    monkeypatch.setattr(ocr, "recognize", _explode)
    result = await ocr.build_image_context(
        [], user_id=uuid.uuid4(), conversation_id=uuid.uuid4()
    )
    assert result == ""
    assert called is False


async def test_engine_unavailable_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ocr, "is_available", lambda: False)
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    result = await ocr.build_image_context(
        [_store_image(user_id, conv_id)], user_id=user_id, conversation_id=conv_id
    )
    assert result == ""


async def test_recognized_text_is_formatted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ocr, "is_available", lambda: True)
    monkeypatch.setattr(ocr, "recognize", lambda path: "ZQ-8891\n林雨桐")
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    result = await ocr.build_image_context(
        [_store_image(user_id, conv_id, "扫描件.png")],
        user_id=user_id,
        conversation_id=conv_id,
    )
    assert result.startswith("【图片 OCR：扫描件.png】")
    assert "ZQ-8891" in result
    assert "林雨桐" in result


async def test_empty_recognition_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """识别不到文字 → 不产出块（上层据此回「未识别到文字」）。"""
    monkeypatch.setattr(ocr, "is_available", lambda: True)
    monkeypatch.setattr(ocr, "recognize", lambda path: "   ")
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    result = await ocr.build_image_context(
        [_store_image(user_id, conv_id)], user_id=user_id, conversation_id=conv_id
    )
    assert result == ""


async def test_long_text_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "is_available", lambda: True)
    monkeypatch.setattr(settings, "OCR_MAX_CHARS", 10)
    monkeypatch.setattr(ocr, "recognize", lambda path: "0123456789abcdefghij")
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    result = await ocr.build_image_context(
        [_store_image(user_id, conv_id)], user_id=user_id, conversation_id=conv_id
    )
    assert "0123456789" in result
    assert "abcdefghij" not in result
    assert "已截断" in result


async def test_missing_file_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """附件定位不到（越权 id / 文件已删）时跳过，不抛异常。"""
    monkeypatch.setattr(ocr, "is_available", lambda: True)
    monkeypatch.setattr(ocr, "recognize", lambda path: "不该被调用")
    meta = [{"id": "0" * 32, "kind": attachments.KIND_IMAGE, "filename": "gone.png"}]
    result = await ocr.build_image_context(
        meta, user_id=uuid.uuid4(), conversation_id=uuid.uuid4()
    )
    assert result == ""


async def test_non_image_entries_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "is_available", lambda: True)
    monkeypatch.setattr(ocr, "recognize", lambda path: "不该被调用")
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    att_id, _ = attachments.store(
        user_id=user_id,
        conversation_id=conv_id,
        payload=b"hello",
        filename="说明.txt",
    )
    meta = [
        {
            "id": att_id,
            "kind": attachments.KIND_DOCUMENT,
            "filename": "说明.txt",
        }
    ]
    result = await ocr.build_image_context(
        meta, user_id=user_id, conversation_id=conv_id
    )
    assert result == ""

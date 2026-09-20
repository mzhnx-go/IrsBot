"""聊天附件上传端点测试（Phase 16 / S1）。

覆盖 POST /agent/attachments：
- 文档：.txt 成功入库并返回解析字符数
- 图片：PNG 魔数识别成功并返回 mime
- 400：不支持的格式、文档解析失败、超过大小上限
- 404：会话不存在 / 会话属于别人
- 401：未带令牌
- 删除会话时附件目录一并清除

落盘根目录用 tmp_path 隔离，绝不在真实 uploads 下留垃圾。
路由在调用时才读 settings，所以函数级 monkeypatch 足够。
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/agent/attachments"
CONV_BASE = f"{settings.API_V1_STR}/agent/conversations"

#: 一张足以通过魔数嗅探的最小 PNG（只认头部 8 字节）
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def attach_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """把附件根目录指到临时目录，测试之间互不干扰。"""
    monkeypatch.setattr(settings, "CHAT_ATTACHMENT_DIR", str(tmp_path))
    yield tmp_path


def _create_conversation(client: TestClient, headers: dict) -> str:
    res = client.post(CONV_BASE, headers=headers, json={})
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _upload(
    client: TestClient,
    headers: dict | None,
    conversation_id: str,
    *,
    filename: str,
    payload: bytes,
    content_type: str = "application/octet-stream",
):
    return client.post(
        BASE,
        headers=headers or {},
        data={"conversation_id": conversation_id},
        files={"file": (filename, payload, content_type)},
    )


# ── 文档 ─────────────────────────────────────────────────────


def test_upload_txt_document_returns_extracted_chars(
    client: TestClient, superuser_token_headers: dict
) -> None:
    conv_id = _create_conversation(client, superuser_token_headers)

    res = _upload(
        client,
        superuser_token_headers,
        conv_id,
        filename="说明.txt",
        payload="第一行\n第二行".encode(),
        content_type="text/plain",
    )

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "document"
    assert body["filename"] == "说明.txt"
    assert body["size"] == len("第一行\n第二行".encode())
    # 解析出的字符数不含换行折叠丢失：至少要有内容
    assert body["extracted_chars"] and body["extracted_chars"] > 0
    assert body["truncated"] is False
    assert body["mime"] is None
    # att_id 是 32 位十六进制，前端 chip 直接回传它
    assert len(body["id"]) == 32 and all(c in "0123456789abcdef" for c in body["id"])


def test_upload_truncates_oversized_document(
    client: TestClient,
    superuser_token_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超长文档按上限截断而不是报错（用户不该因为文档长就传不进来）"""
    monkeypatch.setattr(settings, "ATTACHMENT_MAX_CHARS", 5)
    conv_id = _create_conversation(client, superuser_token_headers)

    res = _upload(
        client,
        superuser_token_headers,
        conv_id,
        filename="长文.txt",
        payload=("字" * 100).encode(),
    )

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["truncated"] is True
    assert body["extracted_chars"] == 5


# ── 图片 ─────────────────────────────────────────────────────


def test_upload_png_image_returns_mime(
    client: TestClient, superuser_token_headers: dict
) -> None:
    conv_id = _create_conversation(client, superuser_token_headers)

    res = _upload(
        client,
        superuser_token_headers,
        conv_id,
        filename="截图.png",
        payload=PNG_BYTES,
        content_type="image/png",
    )

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "image"
    assert body["mime"] == "image/png"
    assert body["extracted_chars"] is None


# ── 400 分支 ─────────────────────────────────────────────────


def test_reject_unsupported_format(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """扩展名不在文档白名单、魔数又不是图片 → 400，且提示受支持格式"""
    conv_id = _create_conversation(client, superuser_token_headers)

    res = _upload(
        client,
        superuser_token_headers,
        conv_id,
        filename="恶意.exe",
        payload=b"MZ\x90\x00",
    )

    assert res.status_code == 400, res.text
    assert "不支持的文件格式" in res.json()["detail"]


def test_reject_lying_extension(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """只改扩展名冒充图片：魔数嗅探必须拦住"""
    conv_id = _create_conversation(client, superuser_token_headers)

    res = _upload(
        client,
        superuser_token_headers,
        conv_id,
        filename="伪装.png",
        payload=b"this is plainly not an image",
    )

    assert res.status_code == 400, res.text


def test_reject_oversized_document(
    client: TestClient,
    superuser_token_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超过大小上限直接拒绝，且不落盘"""
    monkeypatch.setattr(settings, "ATTACHMENT_MAX_DOC_BYTES", 16)
    conv_id = _create_conversation(client, superuser_token_headers)

    res = _upload(
        client,
        superuser_token_headers,
        conv_id,
        filename="大文件.txt",
        payload=b"x" * 1024,
    )

    assert res.status_code == 400, res.text
    assert "大小上限" in res.json()["detail"]


# ── 权限与归属 ───────────────────────────────────────────────


def test_anonymous_rejected(client: TestClient, superuser_token_headers: dict) -> None:
    conv_id = _create_conversation(client, superuser_token_headers)

    res = _upload(
        client, None, conv_id, filename="a.txt", payload=b"hello world"
    )

    assert res.status_code == 401


def test_unknown_conversation_returns_404(
    client: TestClient, superuser_token_headers: dict
) -> None:
    res = _upload(
        client,
        superuser_token_headers,
        str(uuid.uuid4()),
        filename="a.txt",
        payload=b"hello world",
    )

    assert res.status_code == 404


def test_other_users_conversation_returns_404(
    client: TestClient,
    superuser_token_headers: dict,
    normal_user_token_headers: dict,
) -> None:
    """别人的会话一律当作不存在：不泄露"这个 id 是有效的" """
    conv_id = _create_conversation(client, superuser_token_headers)

    res = _upload(
        client,
        normal_user_token_headers,
        conv_id,
        filename="a.txt",
        payload=b"hello world",
    )

    assert res.status_code == 404


# ── 生命周期 ─────────────────────────────────────────────────


def test_deleting_conversation_removes_attachment_dir(
    client: TestClient,
    superuser_token_headers: dict,
    attach_root: Path,
) -> None:
    """删会话即删附件目录，不许留孤儿文件"""
    conv_id = _create_conversation(client, superuser_token_headers)
    res = _upload(
        client,
        superuser_token_headers,
        conv_id,
        filename="a.txt",
        payload=b"hello world",
    )
    assert res.status_code == 201, res.text

    # 根目录下只应有一个用户目录（本用例只上传过一次）
    conv_dirs = list(attach_root.glob(f"*/{conv_id}"))
    assert len(conv_dirs) == 1, conv_dirs
    conv_dir = conv_dirs[0]
    assert any(conv_dir.iterdir())

    deleted = client.delete(f"{CONV_BASE}/{conv_id}", headers=superuser_token_headers)
    assert deleted.status_code == 200, deleted.text
    assert not conv_dir.exists()

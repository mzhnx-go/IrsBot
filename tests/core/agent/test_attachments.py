"""聊天附件基础设施单测（Phase 16 / S1）。

只测纯逻辑与文件系统行为，不碰 HTTP、不碰数据库：
- 文件名净化 / 扩展名白名单
- 图片魔数嗅探（含"扩展名说谎"的用例）
- 落盘 → resolve 的往返，以及 resolve 对非法 att_id 的拒绝
- 文档解析与超长截断

`CHAT_ATTACHMENT_DIR` 被 monkeypatch 到 tmp_path，绝不往仓库里写测试文件。
"""

import uuid
from pathlib import Path

import pytest

from app.core.agent import attachments
from app.core.config import settings

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def attach_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把附件根目录指向临时目录（模块级 settings 是单例，必须打补丁）。

    autouse：补丁是"环境"而非"输入"，用例不该为了生效而多写一个参数。
    需要路径的用例直接用 tmp_path（与这里是同一个目录）。
    """
    monkeypatch.setattr(settings, "CHAT_ATTACHMENT_DIR", str(tmp_path))


# ── 文件名净化 ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("报告.pdf", "报告.pdf"),
        ("a b.txt", "a_b.txt"),
        ("../../etc/passwd", "passwd"),
        (r"..\..\windows\system32\evil.txt", "evil.txt"),
        ("/absolute/path/note.md", "note.md"),
        ("", "unnamed"),
        ("...", "unnamed"),
    ],
)
def test_safe_filename(raw: str, expected: str) -> None:
    assert attachments.safe_filename(raw) == expected


def test_safe_filename_caps_length() -> None:
    assert len(attachments.safe_filename("x" * 500)) <= 120


def test_safe_filename_handles_none() -> None:
    assert attachments.safe_filename(None) == "unnamed"


# ── 扩展名白名单 ───────────────────────────────────────────


@pytest.mark.parametrize("name", ["a.pdf", "a.PDF", "a.txt", "a.md", "a.docx"])
def test_is_allowed_document_true(name: str) -> None:
    assert attachments.is_allowed_document(name)


@pytest.mark.parametrize("name", ["a.exe", "a.png", "a.xlsx", "a", None])
def test_is_allowed_document_false(name: str | None) -> None:
    assert not attachments.is_allowed_document(name)


# ── 图片魔数嗅探 ───────────────────────────────────────────

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
WEBP = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 8


@pytest.mark.parametrize(
    "data,expected",
    [
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
        (GIF, "image/gif"),
        (WEBP, "image/webp"),
    ],
)
def test_sniff_image_mime_recognizes(data: bytes, expected: str) -> None:
    assert attachments.sniff_image_mime(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"hello world",
        b"MZ\x90\x00",  # 伪装成 png 的 exe 头也救不了它——魔数不对就是不认
        b"RIFF\x00\x00\x00\x00AVI ",  # RIFF 但不是 WEBP
        b"\x89PNG",  # 头被截断
    ],
)
def test_sniff_image_mime_rejects(data: bytes) -> None:
    assert attachments.sniff_image_mime(data) is None


# ── 落盘与定位 ─────────────────────────────────────────────


def test_store_then_resolve_roundtrip(tmp_path: Path) -> None:
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    att_id, dest = attachments.store(
        user_id=user_id,
        conversation_id=conv_id,
        payload=b"hello",
        filename="note.txt",
    )

    assert dest.read_bytes() == b"hello"
    # 目录结构 = {root}/{user_id}/{conversation_id}/
    assert dest.parent == tmp_path / str(user_id) / str(conv_id)

    found = attachments.resolve(
        user_id=user_id, conversation_id=conv_id, att_id=att_id
    )
    assert found == dest
    assert attachments.read_bytes(found) == b"hello"


def test_store_sanitizes_filename_in_storage_path() -> None:
    """落盘名必须只含基名——原始名带路径也不能逃出会话目录。"""
    _, dest = attachments.store(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        payload=b"x",
        filename="../../../../tmp/evil.png",
    )
    assert dest.name.endswith("_evil.png")
    assert ".." not in dest.name


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        "not-hex",
        "../../etc/passwd",
        "a" * 31,
        "A" * 32,  # 大写也不算合法（服务端只生成小写 hex）
        "../" + "a" * 32,
    ],
)
def test_resolve_rejects_malformed_att_id(bad_id: str) -> None:
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    attachments.store(
        user_id=user_id,
        conversation_id=conv_id,
        payload=b"x",
        filename="a.png",
    )
    assert (
        attachments.resolve(user_id=user_id, conversation_id=conv_id, att_id=bad_id)
        is None
    )


def test_resolve_is_scoped_to_user_and_conversation() -> None:
    """跨用户 / 跨会话都取不到——这是多租户隔离的落点。"""
    owner, other = uuid.uuid4(), uuid.uuid4()
    conv_a, conv_b = uuid.uuid4(), uuid.uuid4()
    att_id, _ = attachments.store(
        user_id=owner,
        conversation_id=conv_a,
        payload=b"secret",
        filename="s.txt",
    )

    assert attachments.resolve(
        user_id=owner, conversation_id=conv_a, att_id=att_id
    ) is not None
    # 换个用户
    assert (
        attachments.resolve(user_id=other, conversation_id=conv_a, att_id=att_id)
        is None
    )
    # 换个会话
    assert (
        attachments.resolve(user_id=owner, conversation_id=conv_b, att_id=att_id)
        is None
    )


def test_resolve_returns_none_for_unknown_id() -> None:
    assert (
        attachments.resolve(
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            att_id=uuid.uuid4().hex,
        )
        is None
    )


def test_resolve_rejects_duplicate_id_files() -> None:
    """同 id 出现两个文件 = 数据异常，宁可拒绝也不猜。"""
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    att_id, dest = attachments.store(
        user_id=user_id,
        conversation_id=conv_id,
        payload=b"x",
        filename="a.png",
    )
    (dest.parent / f"{att_id}_second.png").write_bytes(b"y")

    assert (
        attachments.resolve(user_id=user_id, conversation_id=conv_id, att_id=att_id)
        is None
    )


# ── 文档解析与截断 ─────────────────────────────────────────


async def test_read_document_text_plain() -> None:
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    _, dest = attachments.store(
        user_id=user_id,
        conversation_id=conv_id,
        payload="第一段\n\n第二段".encode(),
        filename="a.txt",
    )
    text, truncated = await attachments.read_document_text(dest)
    assert "第一段" in text
    assert "第二段" in text
    assert truncated is False


async def test_read_document_text_truncates_over_limit(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ATTACHMENT_MAX_CHARS", 10)
    _, dest = attachments.store(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        payload=b"0123456789abcdefghij",
        filename="a.txt",
    )
    text, truncated = await attachments.read_document_text(dest)
    assert text == "0123456789"
    assert truncated is True


async def test_read_document_text_rejects_unsupported_extension(
    tmp_path: Path,
) -> None:
    """解析器白名单外的扩展名必须报错（端点靠它回 400）。"""
    path = tmp_path / "weird.xlsx"
    path.write_bytes(b"x")
    with pytest.raises(ValueError):
        await attachments.read_document_text(path)


# ── 会话目录清理 ───────────────────────────────────────────


def test_remove_conversation_dir_only_touches_target() -> None:
    user_id = uuid.uuid4()
    conv_a, conv_b = uuid.uuid4(), uuid.uuid4()
    for conv in (conv_a, conv_b):
        attachments.store(
            user_id=user_id,
            conversation_id=conv,
            payload=b"x",
            filename="a.txt",
        )

    attachments.remove_conversation_dir(user_id, conv_a)

    assert not attachments.attachment_dir(user_id, conv_a).exists()
    assert attachments.attachment_dir(user_id, conv_b).is_dir()


def test_remove_conversation_dir_is_idempotent() -> None:
    """目录不存在时不得抛错——删会话不该因为"没有附件"失败。"""
    attachments.remove_conversation_dir(uuid.uuid4(), uuid.uuid4())


# ── 本轮内容拼装（build_turn_content）────────────────────────


async def _store_doc(user_id, conv_id, filename: str, body: str) -> dict:
    att_id, _ = attachments.store(
        user_id=user_id,
        conversation_id=conv_id,
        payload=body.encode(),
        filename=filename,
    )
    return {
        "id": att_id,
        "kind": attachments.KIND_DOCUMENT,
        "filename": filename,
        "size": len(body),
    }


async def _store_image(user_id, conv_id, filename: str, data: bytes) -> dict:
    att_id, _ = attachments.store(
        user_id=user_id,
        conversation_id=conv_id,
        payload=data,
        filename=filename,
    )
    return {
        "id": att_id,
        "kind": attachments.KIND_IMAGE,
        "filename": filename,
        "size": len(data),
    }


async def test_build_turn_content_text_only() -> None:
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    content = await attachments.build_turn_content(
        "你好", [], user_id=user_id, conversation_id=conv_id, supports_vision=False
    )
    assert content == "你好"


async def test_build_turn_content_appends_document_text() -> None:
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    meta = [await _store_doc(user_id, conv_id, "年报.txt", "净利润 12345 万")]
    content = await attachments.build_turn_content(
        "讲了什么", meta, user_id=user_id, conversation_id=conv_id,
        supports_vision=False,
    )
    assert isinstance(content, str)
    assert content.startswith("讲了什么")
    assert "净利润 12345 万" in content
    assert "年报.txt" in content


async def test_build_turn_content_document_only_has_no_fake_user_words() -> None:
    """只发文档不打字：content 里只有文档块，不编造用户话。"""
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    meta = [await _store_doc(user_id, conv_id, "片段.txt", "关键结论：可行")]
    content = await attachments.build_turn_content(
        "", meta, user_id=user_id, conversation_id=conv_id, supports_vision=False
    )
    assert isinstance(content, str)
    assert content.startswith("【附件：片段.txt】")
    assert "关键结论：可行" in content


async def test_build_turn_content_inlines_image_when_vision() -> None:
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    meta = [await _store_image(user_id, conv_id, "图.png", PNG)]
    content = await attachments.build_turn_content(
        "这是什么", meta, user_id=user_id, conversation_id=conv_id,
        supports_vision=True,
    )
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "这是什么"}
    img = content[1]
    assert img["type"] == "image_url"
    # MIME 来自魔数（image/png），base64 里能还原出原字节
    assert img["image_url"]["url"].startswith("data:image/png;base64,")
    import base64

    b64 = img["image_url"]["url"].split(",", 1)[1]
    assert base64.b64decode(b64) == PNG


async def test_build_turn_content_notes_image_when_not_vision() -> None:
    """非视觉模型：不内联字节，改为文字说明——不能让模型凭空看图。"""
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    meta = [await _store_image(user_id, conv_id, "照片.jpg", JPEG)]
    content = await attachments.build_turn_content(
        "这是什么", meta, user_id=user_id, conversation_id=conv_id,
        supports_vision=False,
    )
    assert isinstance(content, str)
    assert "照片.jpg" in content
    assert "不支持图片理解" in content
    assert "base64" not in content


async def test_build_turn_content_image_only_vision_uses_placeholder_text() -> None:
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    meta = [await _store_image(user_id, conv_id, "图.png", PNG)]
    content = await attachments.build_turn_content(
        "", meta, user_id=user_id, conversation_id=conv_id, supports_vision=True
    )
    assert isinstance(content, list)
    assert content[0]["text"] == "（用户只发送了图片）"


async def test_build_turn_content_missing_image_degrades_to_text() -> None:
    """图片文件丢失：不能发出只有文本块的"多模态"，退回字符串。"""
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    meta = [{"id": "0" * 32, "kind": attachments.KIND_IMAGE, "filename": "gone.png"}]
    content = await attachments.build_turn_content(
        "看图", meta, user_id=user_id, conversation_id=conv_id, supports_vision=True
    )
    assert content == "看图"


async def test_build_turn_content_mixed_doc_and_image() -> None:
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    meta = [
        await _store_doc(user_id, conv_id, "说明.txt", "文档正文在此"),
        await _store_image(user_id, conv_id, "图.png", PNG),
    ]
    content = await attachments.build_turn_content(
        "一起看", meta, user_id=user_id, conversation_id=conv_id,
        supports_vision=True,
    )
    assert isinstance(content, list)
    # 文档文本并入文本块，图片单独成块
    assert "文档正文在此" in content[0]["text"]
    assert content[1]["type"] == "image_url"


# ── 元数据反推（describe）────────────────────────────────────


def test_describe_derives_metadata_from_disk() -> None:
    user_id, conv_id = uuid.uuid4(), uuid.uuid4()
    att_id, _ = attachments.store(
        user_id=user_id,
        conversation_id=conv_id,
        payload=b"x",
        filename="报告.pdf",
    )
    meta = attachments.describe(
        user_id=user_id, conversation_id=conv_id, att_id=att_id
    )
    assert meta is not None
    assert meta["id"] == att_id
    assert meta["filename"] == "报告.pdf"
    assert meta["kind"] == attachments.KIND_DOCUMENT
    assert meta["size"] == 1


def test_describe_unknown_id_returns_none() -> None:
    assert (
        attachments.describe(
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            att_id=uuid.uuid4().hex,
        )
        is None
    )

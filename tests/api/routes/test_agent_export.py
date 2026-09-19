"""对话导出 REST API 测试。

覆盖 GET /agent/conversations/{id}/export：
- 五种格式（md / txt / json / docx / pdf）都能拿到可解析的文件
- 省略 format 时默认 Markdown
- 中文标题走 RFC 6266 双写文件名，不炸响应头编码
- 没有消息的空会话也能导出
- 归属校验：不存在 / 别人的会话一律 404，非法格式 422

走真实路由 + 测试数据库；消息直接经 ConversationManager 落库，
不经过 LLM，故不打 integration 标记。
"""

import io
import json
import uuid

import pytest
from app.core.agent.conversation import ConversationManager
from app.core.config import settings
from fastapi.testclient import TestClient
from sqlmodel import Session

BASE = f"{settings.API_V1_STR}/agent/conversations"


def _conversation_with_messages(
    client: TestClient,
    headers: dict,
    db: Session,
    *,
    title: str = "导出测试对话",
    turns: list[tuple[str, str]] | None = None,
) -> str:
    """建会话并写入若干消息，返回会话 id。

    参数:
        client / headers: 已鉴权的测试客户端。
        db: 测试库 Session（用于另开连接写消息）。
        title: 会话标题。
        turns: [(role, text), ...]；None 表示不写任何消息。

    返回:
        会话 id（字符串）。
    """
    res = client.post(BASE, headers=headers, json={"title": title})
    assert res.status_code == 200, res.text
    conv_id = res.json()["id"]

    if turns:
        with Session(db.get_bind()) as session:
            manager = ConversationManager(session)
            for role, text in turns:
                manager.add_message(
                    conv_id=uuid.UUID(conv_id), role=role, content=text
                )
    return conv_id


def _export(client: TestClient, headers: dict, conv_id: str, fmt: str | None = None):
    """调用导出端点；fmt 为 None 时不传 format 参数。"""
    params = {} if fmt is None else {"format": fmt}
    return client.get(f"{BASE}/{conv_id}/export", headers=headers, params=params)


# ── 各格式 ────────────────────────────────────────────────────


def test_export_markdown(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """Markdown：附件响应 + 角色小节 + 正文"""
    conv_id = _conversation_with_messages(
        client,
        superuser_token_headers,
        db,
        turns=[("user", "帮我看看报表"), ("assistant", "先看现金流")],
    )

    res = _export(client, superuser_token_headers, conv_id, "md")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/markdown")
    assert "attachment" in res.headers["content-disposition"]
    body = res.content.decode("utf-8")
    assert body.startswith("# 导出测试对话\n")
    assert "## 用户 · " in body
    assert "## 助手 · " in body
    assert "帮我看看报表" in body
    assert "先看现金流" in body


def test_export_txt(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """纯文本：无 Markdown 标记"""
    conv_id = _conversation_with_messages(
        client, superuser_token_headers, db, turns=[("user", "问题一")]
    )

    res = _export(client, superuser_token_headers, conv_id, "txt")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    body = res.content.decode("utf-8")
    assert "#" not in body
    assert "[用户] " in body
    assert "问题一" in body


def test_export_json(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """JSON：字段结构完整、消息顺序正确"""
    conv_id = _conversation_with_messages(
        client,
        superuser_token_headers,
        db,
        turns=[("user", "问题一"), ("assistant", "回答一")],
    )

    res = _export(client, superuser_token_headers, conv_id, "json")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    data = json.loads(res.content.decode("utf-8"))
    assert data["conversation"]["id"] == conv_id
    assert data["conversation"]["title"] == "导出测试对话"
    assert [m["role"] for m in data["messages"]] == ["user", "assistant"]
    assert data["messages"][0]["content"] == "问题一"


def test_export_docx(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """Word：Content-Type 是 docx 的 MIME，文档可被 python-docx 解析"""
    from docx import Document

    conv_id = _conversation_with_messages(
        client, superuser_token_headers, db, turns=[("user", "问题一")]
    )

    res = _export(client, superuser_token_headers, conv_id, "docx")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    texts = [p.text for p in Document(io.BytesIO(res.content)).paragraphs]
    assert "导出测试对话" in texts
    assert "问题一" in texts


def test_export_pdf(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """PDF：文件头合法，中文可抽回（字体映射正确，不是方框）"""
    from pypdf import PdfReader

    conv_id = _conversation_with_messages(
        client, superuser_token_headers, db, turns=[("assistant", "先看现金流")]
    )

    res = _export(client, superuser_token_headers, conv_id, "pdf")

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    text = PdfReader(io.BytesIO(res.content)).pages[0].extract_text()
    assert "导出测试对话" in text
    assert "先看现金流" in text


def test_export_defaults_to_markdown(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """不传 format 时默认 Markdown"""
    conv_id = _conversation_with_messages(
        client, superuser_token_headers, db, turns=[("user", "问题一")]
    )

    res = _export(client, superuser_token_headers, conv_id)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/markdown")


@pytest.mark.parametrize("fmt", ["md", "txt", "json", "docx", "pdf"])
def test_export_empty_conversation(
    client: TestClient, superuser_token_headers: dict, fmt: str
) -> None:
    """没有消息的新会话同样能导出（不能因为 0 条消息就 500）"""
    res_create = client.post(
        BASE, headers=superuser_token_headers, json={"title": "空会话"}
    )
    conv_id = res_create.json()["id"]

    res = _export(client, superuser_token_headers, conv_id, fmt)

    assert res.status_code == 200
    assert res.content


# ── 文件名 ────────────────────────────────────────────────────


def test_export_filename_uses_conversation_title(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """中文标题走 RFC 6266 双写：ASCII 兜底 + filename* 百分号编码的真名"""
    from urllib.parse import unquote

    res_create = client.post(
        BASE, headers=superuser_token_headers, json={"title": "季度财报/复盘"}
    )
    conv_id = res_create.json()["id"]

    res = _export(client, superuser_token_headers, conv_id, "pdf")

    disposition = res.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    encoded = disposition.split("filename*=UTF-8''", 1)[1]
    # 标题里的 "/" 已被清洗成 "_"，否则会污染文件名
    assert unquote(encoded) == "季度财报_复盘.pdf"
    # 兜底名必须是纯 ASCII，否则响应头编码直接抛异常
    disposition.encode("ascii")


# ── 校验与隔离 ────────────────────────────────────────────────


def test_export_unknown_conversation_404(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """不存在的会话 → 404"""
    res = _export(client, superuser_token_headers, str(uuid.uuid4()), "md")
    assert res.status_code == 404


def test_export_other_users_conversation_404(
    client: TestClient,
    superuser_token_headers: dict,
    normal_user_token_headers: dict,
) -> None:
    """多租户隔离（IDOR 防护）：普通用户导不出别人的会话"""
    res_create = client.post(
        BASE, headers=superuser_token_headers, json={"title": "别人的会话"}
    )
    conv_id = res_create.json()["id"]

    res = _export(client, normal_user_token_headers, conv_id, "md")
    assert res.status_code == 404


def test_export_invalid_format_422(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """非法格式被参数校验挡下（422，而不是生成一个奇怪的文件）"""
    res_create = client.post(
        BASE, headers=superuser_token_headers, json={"title": "格式校验"}
    )
    conv_id = res_create.json()["id"]

    res = _export(client, superuser_token_headers, conv_id, "exe")
    assert res.status_code == 422


def test_export_requires_auth(client: TestClient) -> None:
    """未带令牌 → 401"""
    res = client.get(f"{BASE}/{uuid.uuid4()}/export")
    assert res.status_code == 401
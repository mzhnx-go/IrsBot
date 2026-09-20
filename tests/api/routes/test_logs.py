"""GET /api/v1/logs 端点测试。

覆盖：鉴权三态（匿名 401 / 普通用户 403 / 超管 200）、
`after_id` 游标增量语义、`limit` 截断、**脱敏端到端**
（写进 logger 的明文 Key 在 API 返回中不可见）。
"""

import logging

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.logging import get_ring_handler

LOGS_URL = f"{settings.API_V1_STR}/logs"


def test_requires_auth(client: TestClient) -> None:
    """匿名 401。"""
    r = client.get(LOGS_URL)
    assert r.status_code == 401


def test_forbidden_for_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """普通用户 403 —— 运行日志是超管专属。"""
    r = client.get(LOGS_URL, headers=normal_user_token_headers)
    assert r.status_code == 403


def test_superuser_reads_recent(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """超管 200，结构为 {items, latest_id}，且游标单调不减。"""
    r = client.get(LOGS_URL, headers=superuser_token_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["items"], list)
    assert body["latest_id"] >= len(body["items"])


def test_after_id_returns_only_newer_entries(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """游标增量：拿 latest_id 再拉一次，只应出现之后新写的日志。"""
    r1 = client.get(LOGS_URL, headers=superuser_token_headers)
    latest = r1.json()["latest_id"]

    logging.getLogger("logs-api-test").warning("增量测试标记 unique-marker-9137")

    r2 = client.get(
        LOGS_URL, headers=superuser_token_headers, params={"after_id": latest}
    )
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert items, "游标之后应至少有一条新日志"
    assert all(e["id"] > latest for e in items)
    assert any("unique-marker-9137" in e["message"] for e in items)


def test_limit_truncates(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """limit 生效：缓冲里写 12 条，limit=5 只回 5 条（最新的）。"""
    lg = logging.getLogger("logs-api-test-limit")
    for i in range(12):
        lg.info("limit-test-%d", i)

    r = client.get(
        LOGS_URL, headers=superuser_token_headers, params={"limit": 5}
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 5
    messages = [e["message"] for e in items]
    assert any("limit-test-11" in m for m in messages)  # 取的是最新一端


def test_redaction_end_to_end(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """安全红线：写进 logger 的明文 Key，API 返回里必须不可见。"""
    lg = logging.getLogger("logs-api-test-redact")
    lg.error("upstream call failed key=sk-SUPERsecret99 token=%s", "Bearer aabbccddeeff123")

    r = client.get(LOGS_URL, headers=superuser_token_headers, params={"limit": 2000})
    assert r.status_code == 200
    payload = r.text
    assert "sk-SUPERsecret99" not in payload
    assert "aabbccddeeff123" not in payload
    assert "***REDACTED***" in payload
    # 缓冲本体也不允许有明文（双保险）
    handler = get_ring_handler()
    buffered = str(handler.snapshot(0)[0])
    assert "sk-SUPERsecret99" not in buffered


def test_limit_query_validation(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """limit 越界（>2000 / 0）应 422，不静默吞掉。"""
    for bad in ({"limit": 0}, {"limit": 2001}):
        r = client.get(LOGS_URL, headers=superuser_token_headers, params=bad)
        assert r.status_code == 422, bad

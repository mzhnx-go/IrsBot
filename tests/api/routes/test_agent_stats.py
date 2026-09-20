"""统计端点测试（Phase 15.2e）。

- GET /agent/stats/overview：总计 + 按天序列
- GET /agent/stats/runs：最近运行记录（时间倒序）
- 按用户隔离：他人运行不出现在自己的统计里
- days 参数越界 → 422

AgentRun 直接经 crud 写入，不走 LLM，故不打 integration 标记。
"""

import uuid

from app.core import crud
from app.core.config import settings
from fastapi.testclient import TestClient
from sqlmodel import Session

BASE = f"{settings.API_V1_STR}/agent/stats"


def _user_id(client: TestClient, headers: dict) -> uuid.UUID:
    res = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert res.status_code == 200
    return uuid.UUID(res.json()["id"])


def _mk_run(db: Session, user_id: uuid.UUID, **kw) -> None:
    data = dict(
        status="completed",
        input_text="统计测试输入",
        tokens_used=100,
        tool_calls_made=2,
        duration_ms=1500,
    )
    data.update(kw)
    crud.create_agent_run(db, user_id=user_id, **data)


def test_stats_overview_and_runs(
    client: TestClient,
    db: Session,
    normal_user_token_headers: dict,
) -> None:
    uid = _user_id(client, normal_user_token_headers)
    _mk_run(db, uid)
    _mk_run(
        db, uid, status="failed", tokens_used=50, duration_ms=800,
        tool_calls_made=0,
    )

    res = client.get(
        f"{BASE}/overview?days=7", headers=normal_user_token_headers
    )
    assert res.status_code == 200
    overview = res.json()
    summary = overview["summary"]
    assert summary["runs"] >= 2
    assert summary["completed"] >= 1
    assert summary["failed"] >= 1
    assert summary["tokens"] >= 150
    assert summary["tool_calls"] >= 2
    assert summary["avg_duration_ms"] is not None
    assert any(d["runs"] >= 1 for d in overview["daily"])

    res = client.get(
        f"{BASE}/runs?limit=5", headers=normal_user_token_headers
    )
    assert res.status_code == 200
    runs = res.json()
    assert len(runs) >= 2
    stamps = [r["created_at"] for r in runs]
    assert stamps == sorted(stamps, reverse=True)


def test_stats_isolated_per_user(
    client: TestClient,
    db: Session,
    normal_user_token_headers: dict,
    superuser_token_headers: dict,
) -> None:
    su_uid = _user_id(client, superuser_token_headers)
    marker = "仅超管可见的统计输入"
    _mk_run(db, su_uid, input_text=marker)

    su_runs = client.get(
        f"{BASE}/runs?limit=100", headers=superuser_token_headers
    ).json()
    assert any(r["input_text"] == marker for r in su_runs)

    normal_runs = client.get(
        f"{BASE}/runs?limit=100", headers=normal_user_token_headers
    ).json()
    assert all(r["input_text"] != marker for r in normal_runs)


def test_stats_days_out_of_range(
    client: TestClient, normal_user_token_headers: dict
) -> None:
    res = client.get(
        f"{BASE}/overview?days=0", headers=normal_user_token_headers
    )
    assert res.status_code == 422

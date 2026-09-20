"""日志查询 API —— 控制台页的数据源（**超管专属**）。

进程内环形缓冲（`core/logging.py`）的只读出口：按 `after_id` 游标增量
轮询，首屏用 `after_id=0` 取最近 `limit` 条。不落库，重启即清空——
持久化诉求由 `docker compose logs` 承担（实施计划决策 C1/C2）。
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_active_superuser
from app.core.logging import get_ring_handler

router = APIRouter(prefix="/logs", tags=["logs"])


class LogEntryOut(BaseModel):
    id: int
    ts: float
    level: str
    logger: str
    source: str
    message: str


class LogsOut(BaseModel):
    items: list[LogEntryOut]
    latest_id: int


@router.get(
    "",
    response_model=LogsOut,
    dependencies=[Depends(get_current_active_superuser)],
)
def read_logs(
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
) -> LogsOut:
    """读取运行日志（**超管专属**）。

    Args:
        after_id: 游标。传 0 取最近 `limit` 条（首屏）；传上次响应的
            `latest_id` 则只返回之后的新增条目（增量轮询）。
        limit: 单次最多返回条数。

    Returns:
        日志条目与最新游标（下次轮询的 `after_id`）。
    """
    handler = get_ring_handler()
    if after_id > 0:
        items, latest_id = handler.snapshot(after_id)
        items = items[-limit:]
    else:
        items, latest_id = handler.recent(limit)
    return LogsOut(
        items=[LogEntryOut(**entry) for entry in items], latest_id=latest_id
    )

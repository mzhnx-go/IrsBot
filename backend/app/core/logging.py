"""统一日志配置 + 内存环形缓冲 + 敏感信息脱敏。

对应实施计划 `plan/console-logging-plan.md` Phase L1。

三个职责，一个模块：

1. **setup_logging()**：接管 root 与 uvicorn 系 logger，统一格式与级别。
   ⚠️ uvicorn 自带 handler，不在 `uvicorn.*` 上关 propagate 并挂自有
   handler 的话，访问日志与启动日志根本不会流经我们的缓冲。
2. **RingBufferHandler**：进程内环形缓冲（deque maxlen），每条记录带
   单调递增 id，供 `GET /api/v1/logs` 按 `after_id` 增量轮询。
   持久化交给 `docker compose logs`，本项目不落库不写文件。
3. **redact()**：敏感信息脱敏（实现计划 §8.6 保留项「api_key 不进日志」）。
   做在 handler 层对所有记录兜底，不依赖每个调用点自觉。
"""

import logging
import re
import threading
from collections import deque
from pathlib import Path

# 环形缓冲容量：控制台页回看足够，且内存占用有硬上限（每条约 0.5KB）
RING_BUFFER_SIZE = 2000

# 噪声过滤：控制台页每 2 秒轮询一次 /api/v1/logs，健康检查每 30 秒一次——
# 这些访问日志进缓冲会形成「自我回声」，把有效信息冲掉（实测控制台被
# uvicorn.access 淹没）。命中即不进缓冲（参考 AstrBot 控制台「排除噪声」思路）。
_NOISE_ACCESS_MARKERS = (
    "/api/v1/logs",
    "/api/v1/utils/health-check",
)

# 脱敏规则：命中即值替换为 ***REDACTED***，不保留部分明文。
# - sk- 开头的 Key（OpenAI / DeepSeek / SiliconFlow 等主流厂商格式）
# - Bearer Token（Authorization 头，lookbehind 保住 "Bearer " 前缀）
# - api_key / api-key 的 query / 表单 / JSON 形态（group(1) 保留键名前缀）
# - enc:v1: 开头的库内密文（API Key 加密落库格式）
_REDACT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?<=Bearer )[A-Za-z0-9._\-]{8,}"),
    re.compile(
        r"(?i)(api[_-]?key[\"']?\s*[=:]\s*[\"']?)[^\s\"',&}]+"
    ),
    re.compile(r"enc:v1:[A-Za-z0-9+/=_\-]{8,}"),
]

_REDACTED = "***REDACTED***"


def _source_location(record: logging.LogRecord) -> str:
    """提取「父目录.文件名:行号」形态的来源定位（AstrBot 风格）。

    完整路径太长会撑爆控制台；只取 `core.agent:112` 这类短形态已够定位。
    uvicorn 等外部库的记录同样可定位（如 `protocols.http11:399`）。
    """
    try:
        path = Path(record.pathname)
        return f"{path.parent.name}.{path.stem}:{record.lineno}"
    except Exception:  # noqa: BLE001 —— 定位失败不挡日志
        return ""


def redact(text: str) -> str:
    """对一段文本做敏感信息脱敏（纯函数，供单测穷举）。

    Args:
        text: 原始日志文本。

    Returns:
        敏感片段已替换为 ***REDACTED*** 的文本（键名前缀保留，
        便于运维仍能看出「这里是哪个字段被脱了」）。
    """
    for pattern in _REDACT_PATTERNS:
        text = pattern.sub(
            lambda m: (m.group(1) + _REDACTED) if m.lastindex else _REDACTED,
            text,
        )
    return text


class SensitiveDataFilter(logging.Filter):
    """logging.Filter：在记录进入 handler 前对消息脱敏。

    挂在 RingBufferHandler 上（而非 root logger），保证只影响进缓冲的
    副本——控制台/文件里看到的永远是脱敏后的，不改写调用方自己的对象。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        # args 会在 % 格式化时拼进消息，一并脱敏（api_key=%s 这类写法）
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        elif record.args:
            record.args = redact(str(record.args))
        return True


class LogEntry(dict):
    """环形缓冲里的一条日志（dict 子类，直接可 JSON 序列化）。"""


class RingBufferHandler(logging.Handler):
    """进程内环形缓冲 handler。

    线程安全：logging 调用可能来自任意线程（工具子进程回调、
    uvicorn worker），deque 自身的 append 是原子的，但「取游标、
    批量读」与「追加」并发时需要锁保护快照一致性。
    """

    def __init__(self, capacity: int = RING_BUFFER_SIZE) -> None:
        super().__init__()
        self._buffer: deque[LogEntry] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._next_id = 0
        # 脱敏做在本 handler 上，进缓冲前兜底（决策 C3）
        self.addFilter(SensitiveDataFilter())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # 噪声过滤：访问日志里的自轮询/健康检查不进缓冲（见 _NOISE_ACCESS_MARKERS）
            if record.name == "uvicorn.access" and any(
                marker in record.getMessage() for marker in _NOISE_ACCESS_MARKERS
            ):
                return
            # 用 getMessage() 取纯消息文本：结构化字段（ts/level/logger）已单独存，
            # 再走 self.format() 会把格式化前缀重复拼进 message。
            # 异常堆栈单独追加（traceback 不在 message 里，丢了就排不了错）。
            message = record.getMessage()
            if record.exc_info:
                message += "\n" + _EXCEPTION_FORMATTER.formatException(
                    record.exc_info
                )
        except Exception:  # noqa: BLE001 —— format 失败不能拖垮业务线程
            return
        with self._lock:
            self._next_id += 1
            entry: LogEntry = LogEntry(
                id=self._next_id,
                ts=record.created,
                level=record.levelname,
                logger=record.name,
                source=_source_location(record),
                message=message,
            )
            self._buffer.append(entry)

    def snapshot(self, after_id: int = 0) -> tuple[list[LogEntry], int]:
        """取 `after_id` 之后的日志快照与最新 id（供轮询 API）。"""
        with self._lock:
            items = [e for e in self._buffer if e["id"] > after_id]
            return items, self._next_id

    def recent(self, limit: int = 500) -> tuple[list[LogEntry], int]:
        """取最近 `limit` 条（首屏用），返回 (条目, 最新游标)。"""
        with self._lock:
            items = list(self._buffer)[-limit:]
            return items, self._next_id


# 进程级单例：routes 与 setup_logging 共用同一份缓冲
_ring_handler: RingBufferHandler | None = None


def get_ring_handler() -> RingBufferHandler:
    """取全局环形缓冲 handler（惰性创建，测试与运行共用一份）。"""
    global _ring_handler
    if _ring_handler is None:
        _ring_handler = RingBufferHandler()
    return _ring_handler


_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
# emit 里只取纯消息文本，Formatter 仅用于拼异常堆栈（Handler 没有 formatException）
_EXCEPTION_FORMATTER = logging.Formatter()


def setup_logging(level: str = "INFO") -> None:
    """配置全局日志：格式、级别、环形缓冲、uvicorn 接管。

    Idempotent：重复调用不产生重复 handler（uvicorn reload、测试
    多次 import 都安全）。

    Args:
        level: root logger 级别，来自 settings.LOG_LEVEL。
    """
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = get_ring_handler()

    if handler not in root.handlers:
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)

    # uvicorn 系 logger 自带 handler，必须关 propagate 才不会双写；
    # 同时它们也要进我们的缓冲 —— 统一交给 root（propagate=True → root
    # 的 RingBufferHandler 收得到），只移除它们各自的默认 handler 防止
    # 控制台重复输出。uvicorn.access 关闭 propagate（访问日志量大且
    # 噪音高，进缓冲但不重复打印）。
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = True

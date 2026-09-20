"""core/logging.py 纯逻辑单测：脱敏正则 + 环形缓冲 + setup_logging。

不依赖 FastAPI/DB；handler 行为用**新建实例**测，不碰全局单例
（全局单例被 setup_logging 挂到 root 上，测试里污染会影响别的用例）。
"""

import logging

from app.core.logging import (
    RING_BUFFER_SIZE,
    RingBufferHandler,
    SensitiveDataFilter,
    redact,
    setup_logging,
)

# ── redact 纯函数 ──────────────────────────────────────────────


def test_redact_sk_key() -> None:
    """主流厂商 sk- 格式 Key 整体替换，不留部分明文。"""
    out = redact("calling with sk-abc123XYZ_def-456ghi done")
    assert "abc123XYZ" not in out
    assert "***REDACTED***" in out


def test_redact_bearer_token() -> None:
    out = redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.token.part")
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert "***REDACTED***" in out


def test_redact_api_key_query_form() -> None:
    """api_key= / api-key: / API_KEY = 各种写法都要命中。"""
    for snippet in (
        "GET /v1/x?api_key=secret12345",
        "api-key: secret12345",
        "API_KEY = secret12345",
        '{"api_key":"secret12345"}',
    ):
        assert "secret12345" not in redact(snippet), snippet


def test_redact_enc_v1_ciphertext() -> None:
    out = redact("stored key enc:v1:AbCdEf123456== ok")
    assert "AbCdEf123456" not in out


def test_redact_keeps_plain_text() -> None:
    """普通文本、不含敏感信息时原样返回（不能误伤正常运维内容）。"""
    assert redact("Agent 轮次完成，2 次工具调用") == "Agent 轮次完成，2 次工具调用"


def test_redact_empty_string() -> None:
    assert redact("") == ""


def test_redact_multiple_secrets_in_one_line() -> None:
    line = "key1=sk-aaaaaaaa1 key2=sk-bbbbbbbb2"
    out = redact(line)
    assert "aaaaaaaa1" not in out and "bbbbbbbb2" not in out
    assert out.count("***REDACTED***") == 2


def test_redact_sk_too_short_not_matched() -> None:
    """`sk-` 后不足 8 位不是 Key（如普通词），不误伤。"""
    assert redact("task-sk-1 ok") == "task-sk-1 ok"


# ── SensitiveDataFilter ────────────────────────────────────────


def test_filter_redacts_msg_and_args() -> None:
    """消息本体与 % 格式化 args 都要过脱敏。"""
    f = SensitiveDataFilter()
    rec = logging.LogRecord(
        "t", logging.INFO, "p", 1, "using key %s", ("sk-aaaaaaaa1",), None
    )
    assert f.filter(rec) is True
    assert "aaaaaaaa1" not in rec.getMessage()


# ── RingBufferHandler ──────────────────────────────────────────


def _make_logger(name: str, handler: logging.Handler) -> logging.Logger:
    lg = logging.getLogger(name)
    lg.setLevel(logging.DEBUG)
    lg.handlers = [handler]
    lg.propagate = False
    return lg


def test_ring_buffer_assigns_monotonic_ids() -> None:
    handler = RingBufferHandler()
    lg = _make_logger("rb-test-1", handler)
    for i in range(3):
        lg.info("msg %d", i)
    items, latest = handler.snapshot(0)
    assert [e["id"] for e in items] == [1, 2, 3]
    assert latest == 3


def test_ring_buffer_snapshot_after_id_incremental() -> None:
    handler = RingBufferHandler()
    lg = _make_logger("rb-test-2", handler)
    lg.info("first")
    _, latest = handler.snapshot(0)
    lg.info("second")
    items, latest2 = handler.snapshot(latest)
    assert [e["message"] for e in items] == ["second"]
    assert latest2 == latest + 1


def test_ring_buffer_recent_limit() -> None:
    handler = RingBufferHandler()
    lg = _make_logger("rb-test-3", handler)
    for i in range(10):
        lg.info("n%d", i)
    items, _ = handler.recent(3)
    assert [e["message"] for e in items] == ["n7", "n8", "n9"]


def test_ring_buffer_overflow_drops_oldest() -> None:
    handler = RingBufferHandler(capacity=5)
    lg = _make_logger("rb-test-4", handler)
    for i in range(8):
        lg.info("n%d", i)
    items, _ = handler.snapshot(0)
    assert len(items) == 5
    assert items[0]["message"] == "n3"


def test_ring_buffer_default_capacity_is_project_constant() -> None:
    assert RingBufferHandler()._buffer.maxlen == RING_BUFFER_SIZE == 2000


def test_ring_buffer_redacts_before_storing() -> None:
    """进缓冲前脱敏 —— 端点返回什么，缓冲里就是什么。"""
    handler = RingBufferHandler()
    lg = _make_logger("rb-test-5", handler)
    lg.info("key=sk-aaaaaaaa1")
    (entry,) = handler.snapshot(0)[0]
    assert "aaaaaaaa1" not in entry["message"]


def test_ring_buffer_noise_access_logs_dropped() -> None:
    """自轮询（/api/v1/logs）与健康检查的访问日志不进缓冲（自我回声噪声）。"""
    handler = RingBufferHandler()
    lg = _make_logger("uvicorn.access", handler)
    lg.info('172.18.0.1:1 - "GET /api/v1/logs?after_id=1 HTTP/1.1" 200')
    lg.info('172.18.0.1:2 - "GET /api/v1/utils/health-check/ HTTP/1.1" 200')
    lg.info('172.18.0.1:3 - "POST /api/v1/login/access-token HTTP/1.1" 200')
    items, _ = handler.snapshot(0)
    assert len(items) == 1  # 只剩登录访问日志
    assert "login" in items[0]["message"]


def test_ring_buffer_source_location() -> None:
    """来源字段为「父目录.文件名:行号」形态，可定位且不撑爆控制台。"""
    handler = RingBufferHandler()
    lg = _make_logger("rb-test-src", handler)
    lg.info("hello")
    (entry,) = handler.snapshot(0)[0]
    assert entry["source"], "source 不应为空"
    assert ":" in entry["source"]
    # 形如 `core.test_logging_redact:NNN`，不含完整路径
    assert "/" not in entry["source"] and "\\" not in entry["source"]


def test_setup_logging_is_idempotent() -> None:
    """重复调用不叠加 handler（uvicorn reload / 测试多 import 场景）。"""
    setup_logging("INFO")
    after_first = len(logging.getLogger().handlers)
    setup_logging("INFO")
    assert len(logging.getLogger().handlers) == after_first


def test_setup_logging_uvicorn_propagate() -> None:
    """uvicorn 系 logger 必须被接管（handler 清空、交给 root）。"""
    setup_logging("INFO")
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        assert lg.handlers == [], name
        assert lg.propagate is True, name

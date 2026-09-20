"""内部钩子总线（Phase 12.4 精简版）.

只保留 3 个内部切点，供 Playground 调试回显、统计采集（Phase 14.3）
与未来扩展使用；**不做**第三方插件注册接口，钩子异常一律吞掉，
绝不影响主管线。

钩子清单:
    on_llm_request  — LLM 调用前（参数: messages, model 信息由调用方附带）
    on_llm_response — LLM 返回后（参数: response）
    on_agent_done   — 一次 Agent 运行结束（参数: result）
"""

import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

HookFn = Callable[..., Any]

#: 本项目定义的全部内部钩子名（超出名单的注册一律拒绝，防拼写漂移）
HOOK_NAMES = ("on_llm_request", "on_llm_response", "on_agent_done")


class HookBus:
    """极简异步钩子总线：注册回调 + 事件分发.

    - 回调可为同步或异步函数；
    - emit 时逐个调用，单个回调抛异常只记日志不中断；
    - 未注册任何回调的事件直接跳过，零开销。
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookFn]] = {name: [] for name in HOOK_NAMES}

    def register(self, name: str, fn: HookFn) -> None:
        """注册钩子回调；未知名与重复注册直接拒绝."""
        if name not in self._hooks:
            raise ValueError(f"未知钩子: {name}，允许的钩子: {HOOK_NAMES}")
        if fn not in self._hooks[name]:
            self._hooks[name].append(fn)

    def unregister(self, name: str, fn: HookFn) -> None:
        """注销钩子回调（不存在则静默）."""
        if name in self._hooks:
            try:
                self._hooks[name].remove(fn)
            except ValueError:
                pass

    async def emit(self, name: str, *args: Any, **kwargs: Any) -> None:
        """触发钩子；异常吞掉只记日志，保证不中断主管线."""
        for fn in self._hooks.get(name, []):
            try:
                result = fn(*args, **kwargs)
                if inspect.isawaitable(result):
                    await result
            except Exception:  # noqa: BLE001 — 钩子故障不能拖垮主流程
                logger.exception("钩子 %s 执行失败（已忽略）", name)


#: 进程级共享钩子总线
hook_bus = HookBus()

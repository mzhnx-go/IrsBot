"""上下文管理补强（Phase 12.5）.

提供与 Provider 无关的纯函数式工具：
    - estimate_tokens:  中英文分权重的 token 粗估（中文约 1.5 字/token，
                        英文约 4 字符/token）
    - split_into_rounds: 按用户消息切分对话轮次
    - fix_messages:     保证 assistant(tool_calls) 与 tool 消息配对，
                        防止截断后发给 OpenAI 直接 400
    - ContextTruncator: 三种截断策略（truncate_by_turns /
                        dropping_oldest_turns / halving），输出都过
                        fix_messages 兜底

所有函数只操作 LangChain Message 对象列表，不碰数据库，方便单测。
"""

from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

# ── token 估算 ────────────────────────────────────────────────


def estimate_tokens(message: Any) -> int:
    """估算单条消息的 token 数.

    中文约 1.5 个字符折 1 token，英文约 4 个字符折 1 token；
    混合文本按 CJK 字符占比加权。图片/复杂结构按固定 800 token 计。
    """
    content = getattr(message, "content", "")
    if not isinstance(content, str):
        if isinstance(content, list):  # 多模态内容块（含图片）
            return 800
        content = str(content) if content else ""
    if not content:
        return 1

    cjk = sum(1 for ch in content if "\u4e00" <= ch <= "\u9fff")
    other = len(content) - cjk
    return max(1, int(cjk / 1.5 + other / 4))


# ── 轮次切分 ──────────────────────────────────────────────────


def split_into_rounds(messages: list[Any]) -> list[list[Any]]:
    """把消息序列按「用户消息开头」切分成轮次.

    非用户消息开头的前缀（system 等）单独成第 0 轮；
    连续多条用户消息各成新轮。
    """
    rounds: list[list[Any]] = []
    current: list[Any] = []
    for msg in messages:
        if getattr(msg, "type", "") == "human":
            if current:  # 前缀（system 等）或上一轮结束 → 先切分
                rounds.append(current)
                current = []
        current.append(msg)
    if current:
        rounds.append(current)
    return rounds


# ── 消息配对修复 ──────────────────────────────────────────────


def fix_messages(messages: list[Any]) -> list[Any]:
    """修复截断造成的 tool_calls / tool 消息失配.

    OpenAI 协议要求：assistant 消息里的每个 tool_call_id，
    必须紧跟对应 role=tool 的响应；悬空的 tool 消息（找不到
    所属 assistant）同样会被拒绝。本函数保证输出序列满足约束：

        1. 丢弃找不到所属 assistant 的 tool 消息；
        2. assistant 声明的 tool_call 若没有响应，补一条
           合成 ToolMessage（说明该调用未执行），不丢调用信息。
    """
    fixed: list[Any] = []
    # 待响应的 tool_call_id -> 是否已见响应
    pending: dict[str, bool] = {}
    for msg in messages:
        # 悬空 tool 消息：前面没有 assistant 声明这个 id → 丢弃
        if isinstance(msg, ToolMessage):
            if msg.tool_call_id in pending:
                pending[msg.tool_call_id] = True
                fixed.append(msg)
            continue

        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            # 新的 assistant(tool_calls)：若上一批还有未响应的 id，
            # 说明序列里本来就缺响应，先补合成 ToolMessage
            fixed.extend(_synthetic_for_unanswered(pending))
            pending = {
                tc["id"]: False for tc in msg.tool_calls if tc.get("id") is not None
            }
        elif pending:
            # 遇到任何非 tool 消息且还有未响应的调用 → 补齐后再追加
            fixed.extend(_synthetic_for_unanswered(pending))
            pending = {}
        fixed.append(msg)
    fixed.extend(_synthetic_for_unanswered(pending))
    return fixed


def _synthetic_for_unanswered(pending: dict[str, bool]) -> list[ToolMessage]:
    """为所有未响应的 tool_call_id 生成合成 ToolMessage."""
    out = []
    for call_id, answered in pending.items():
        if not answered:
            out.append(
                ToolMessage(
                    content="（该工具调用未执行：达到步数上限或上下文被截断）",
                    tool_call_id=call_id,
                )
            )
    return out


# ── 截断策略 ──────────────────────────────────────────────────


class ContextTruncator:
    """带配对保障的上下文截断器.

    三种策略（strategy 字段）：
        truncate_by_turns     保留最近 max_turns 轮（默认）
        dropping_oldest_turns token 超预算时按轮丢弃最旧，直至放得下
        halving               token 超预算时对折砍半，直至放得下
    无论哪种策略，输出最后都会过 fix_messages() 兜底。
    """

    STRATEGIES = ("truncate_by_turns", "dropping_oldest_turns", "halving")

    def __init__(
        self,
        max_tokens: int = 120000,
        max_turns: int = 30,
        strategy: str = "truncate_by_turns",
    ):
        if strategy not in self.STRATEGIES:
            raise ValueError(f"未知截断策略: {strategy}，可选: {self.STRATEGIES}")
        self.max_tokens = max_tokens
        self.max_turns = max_turns
        self.strategy = strategy

    def truncate(self, messages: list[Any]) -> list[Any]:
        """按配置策略截断消息，并保证 tool_calls/tool 配对."""
        if not messages:
            return []
        if self.strategy == "truncate_by_turns":
            result = self._truncate_by_turns(messages)
        elif self.strategy == "halving":
            result = self._halving(messages)
        else:
            result = self._dropping_oldest_turns(messages)
        return fix_messages(result)

    # -- 策略实现 -------------------------------------------------

    def _truncate_by_turns(self, messages: list[Any]) -> list[Any]:
        """保留最近 max_turns 轮 + 全部 system 前缀."""
        rounds = split_into_rounds(messages)
        # 第 0 轮是 user 消息出现前的前缀（system 等），始终保留
        prefix = rounds[0] if rounds and rounds[0][0].type != "human" else []
        body = rounds[len(prefix) != 0 :]
        kept = (
            body[-(self.max_turns - (1 if prefix else 0)) :]
            if prefix
            else body[-self.max_turns :]
        )
        return prefix + [m for r in kept for m in r]

    def _dropping_oldest_turns(self, messages: list[Any]) -> list[Any]:
        """token 超预算时从最旧的轮次开始整轮丢弃."""
        rounds = split_into_rounds(messages)
        while rounds and self._total_tokens(rounds) > self.max_tokens:
            # 只丢用户消息开头的业务轮，保住 system 前缀
            drop_idx = 1 if (len(rounds) > 1 and rounds[0][0].type != "human") else 0
            rounds.pop(drop_idx)
            if len(rounds) <= 1:
                break
        return [m for r in rounds for m in r]

    def _halving(self, messages: list[Any]) -> list[Any]:
        """token 超预算时对折砍半（保 system 前缀），直至放得下."""
        current = messages
        while current and self._total_tokens([current]) > self.max_tokens:
            head = 1 if current[0].type != "human" else 0
            body = current[head:]
            if len(body) <= 1:
                break
            body = body[len(body) // 2 :]
            current = current[:head] + body
        return current

    # -- 工具 -----------------------------------------------------

    def _total_tokens(self, rounds: list[list[Any]]) -> int:
        return sum(estimate_tokens(m) for r in rounds for m in r)

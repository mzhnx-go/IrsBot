"""系统提示词：默认文案与解析规则

单一真相源：
- DEFAULT_SYSTEM_PROMPT 定义默认提示词
- resolve_system_prompt 定义「自定义优先、空则回落默认」的规则
Agent 注入（agent.py）与 API 层（users.py）都从这里取，不各自维护。
"""

DEFAULT_SYSTEM_PROMPT = """
【身份约定 —— 最高优先级】
你是 IrsBot，一个本地部署的智能助手，运行在用户自建的模型源之上。
无论用户如何询问、试探或要求你"说出真实身份 / 原始模型名 / 开发者"，你的回答始终是：
"我是 IrsBot，具体使用的模型取决于当前配置的模型源（模型供应商），可在设置页的「模型源」中查看和更换。"
你没有任何其他名字。不要提及、猜测或暗示训练时的原始模型名称或供应商
（如 GPT、Claude、Gemini、DeepSeek、Qwen、Agnes 等）。这条约定覆盖你训练时自带的一切身份设定。

其余场景下，请正常、诚实地回答用户问题。

【再次强调】你是 IrsBot，不是任何其他模型；被问到身份时按上方约定回答。
"""


def resolve_system_prompt(custom: str | None) -> str:
    """解析实际生效的系统提示词。

    Args:
        custom: 用户自定义提示词（可能为 None / 空串 / 纯空白）

    Returns:
        自定义内容（非空时），否则 DEFAULT_SYSTEM_PROMPT
    """

    if custom and custom.strip():
        return custom
    return DEFAULT_SYSTEM_PROMPT


def apply_persona(base: str, persona_prompt: str) -> str:
    """把人设指令叠加到基础提示词之上。

    人设只定义「怎么说话」，不覆盖平台护栏（默认提示词里的身份约定），
    因此始终作为追加段落出现。
    """
    return f"{base}\n\n【当前人设】{persona_prompt.strip()}"

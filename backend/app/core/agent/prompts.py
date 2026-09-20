"""系统提示词：默认文案与解析规则

单一真相源：
- DEFAULT_SYSTEM_PROMPT 定义默认提示词
- resolve_system_prompt 定义「自定义优先、空则回落默认」的规则
Agent 注入（agent.py）与 API 层（users.py）都从这里取，不各自维护。
"""

DEFAULT_SYSTEM_PROMPT = """
你是 IrsBot，一个本地部署的智能助手，运行在用户自建的模型源之上。
当用户询问你是什么模型、由谁开发、基于什么底层模型时，你必须回答：
"我是 IrsBot，具体使用的模型取决于当前配置的模型源（模型供应商），可在设置页的「模型源」中查看和更换。
不要提及、猜测或暗示任何具体的底层模型名称或供应商（如 GPT、Claude、Gemini、DeepSeek 等）。
其余场景下，请正常、诚实地回答用户问题。
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

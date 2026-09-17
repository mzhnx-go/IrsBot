"""分块器 — AstrBot 风格的中文友好分块（基于 LangChain 实现）

相比 LangChain 默认配置的增强点：
1. 中文友好分隔符（"。"、"！" 优先于英文标点）
2. Markdown 标题路径上下文（检索命中时知道属于哪个章节）
3. 代码块保护（``` 内的 # 不会被误判为标题）
"""

import re

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

CHINESE_SEPARATORS = [
    "\n\n",  # 段落（最粗，语义最完整）
    "\n",    # 换行
    "。",    # 中文句号
    "！",    # 中文感叹号
    "？",    # 中文问号
    "，",    # 中文逗号
    ". ",    # 英文句号+空格
    ", ",    # 英文逗号+空格
    " ",     # 单词边界
    "",      # 单字符兜底（保证超长无标点文本也能切开）
]

_CODE_FENCE_RE = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)")

def _mask_code_fences(text: str) -> tuple[str, list[str]]:
    """把代码块替换成占位符，避免内部的 # 被误判为标题

    Returns:
        (替换后的文本, 代码块原文列表)
    """
    fences: list[str] = []

    def _repl(match: re.Match) -> str:
        fences.append(match.group(0))
        # 注意：不能用 \x00 等控制字符做占位符，
        # MarkdownHeaderTextSplitter 会把它们过滤掉导致内容丢失。
        # ⟦⟧ 是 Unicode 方括号，无 Markdown 含义，能安全存活。
        return f"⟦CODEBLOCK{len(fences) - 1}⟧"

    return _CODE_FENCE_RE.sub(_repl, text), fences


def _restore_code_fences(text: str, fences: list[str]) -> str:
    """把占位符还原成代码块原文"""
    return re.sub(
        r"⟦CODEBLOCK(\d+)⟧",
        lambda m: fences[int(m.group(1))],
        text,
    )


class Chunkers:
    """文档分块器"""

    @staticmethod
    def recursive_character(
        documents: list[Document],
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> list[Document]:
        """递归字符分割（通用策略，中文友好）

        LangChain 的 RecursiveCharacterTextSplitter 本身就实现了
        AstrBot RecursiveCharacterChunker 的递归算法，
        只需注入中文分隔符即可，不用重写。
        """
        splitter = RecursiveCharacterTextSplitter(
            separators=CHINESE_SEPARATORS,
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            length_function=len,
        )
        return splitter.split_documents(documents)

    @staticmethod
    def markdown(
        documents: list[Document],
        chunk_size: int = 500,
        overlap: int = 50,
        include_heading_context: bool = True,
    ) -> list[Document]:
        """Markdown 结构感知分块

        流程（对应 AstrBot 的 MarkdownChunker）：
        1. 掩码代码块（防止 # comment 被误判为标题）
        2. 按标题切分（# / ## / ###）
        3. 还原代码块
        4. 拼接标题路径上下文（"安装指南 > 依赖"）
        5. 超长 section 二次递归分割
        """
        header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        )
        size_splitter = RecursiveCharacterTextSplitter(
            separators=CHINESE_SEPARATORS,
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            length_function=len,
        )

        result: list[Document] = []
        for doc in documents:
            # 1. 掩码代码块
            masked, fences = _mask_code_fences(doc.page_content)

            # 2. 按标题切分
            sections = header_splitter.split_text(masked)

            for section in sections:
                # 3. 还原代码块（占位符只在本 section 里的会被替换）
                content = _restore_code_fences(section.page_content, fences)

                # 4. 标题路径上下文
                if include_heading_context:
                    heading_path = " > ".join(
                        v for k, v in section.metadata.items()
                        if k in ("h1", "h2", "h3")
                    )
                    if heading_path:
                        content = f"{heading_path}\n\n{content}"

                # 5. 合并 metadata，二次分割超长 section
                merged_meta = {**doc.metadata, **section.metadata}
                section_doc = Document(page_content=content, metadata=merged_meta)
                result.extend(size_splitter.split_documents([section_doc]))

        return result



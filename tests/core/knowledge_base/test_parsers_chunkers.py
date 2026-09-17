"""Task 7.1 单元测试 — 文档解析器 + 分块器

不需要 Milvus / Embedding API / 数据库，纯函数测试。
"""

import pytest
from app.core.knowledge_base.chunkers import (
    Chunkers,
    _mask_code_fences,
    _restore_code_fences,
)
from app.core.knowledge_base.parsers import DocumentParser
from langchain_core.documents import Document

# ═══════════════ 解析器测试 ═══════════════


class TestDocumentParser:
    @pytest.mark.asyncio
    async def test_parse_txt(self, tmp_path):
        """解析 .txt：整个文件一个 Document"""
        f = tmp_path / "note.txt"
        f.write_text("退货政策：7天内可退。", encoding="utf-8")

        docs = await DocumentParser.parse(str(f))
        assert len(docs) == 1
        assert "7天内可退" in docs[0].page_content
        assert docs[0].metadata["source"].endswith("note.txt")

    @pytest.mark.asyncio
    async def test_parse_markdown_as_text(self, tmp_path):
        """解析 .md：按纯文本处理，内容完整"""
        f = tmp_path / "guide.md"
        f.write_text("# 标题\n\n正文内容。", encoding="utf-8")

        docs = await DocumentParser.parse(str(f))
        assert len(docs) == 1
        assert "# 标题" in docs[0].page_content

    @pytest.mark.asyncio
    async def test_parse_unsupported_extension(self, tmp_path):
        """不支持的格式 → ValueError"""
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8")  # 假装是图片

        with pytest.raises(ValueError, match="不支持的文件格式"):
            await DocumentParser.parse(str(f))

    @pytest.mark.asyncio
    async def test_parse_file_not_found(self, tmp_path):
        """文件不存在 → FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            await DocumentParser.parse(str(tmp_path / "no_such.txt"))


# ═══════════════ 递归分割测试 ═══════════════


class TestRecursiveCharacter:
    def test_short_text_single_chunk(self):
        """短文本 → 一块，不切分"""
        doc = Document(page_content="很短的文本。")
        chunks = Chunkers.recursive_character([doc], chunk_size=500, overlap=0)
        assert len(chunks) == 1
        assert "很短的文本" in chunks[0].page_content

    def test_long_chinese_text_split_at_sentence(self):
        """长中文文本 → 在句号处切分（验证中文分隔符生效）

        构造 40 句话，每句 20 字符。chunk_size=200 时应切成多块，
        且块长是 20 的倍数（句子没被腰斩，overlap=0 时）。
        """
        sentence = "这是一段用来测试中文分块效果的示例句子。"
        text = sentence * 40  # 40 句，约 880 字符
        doc = Document(page_content=text)

        chunks = Chunkers.recursive_character([doc], chunk_size=200, overlap=0)
        assert len(chunks) > 1  # 确实被切了

        for chunk in chunks:
            content = chunk.page_content
            # 每句去掉句号后是 19 字符。
            # 若句子被腰斩，去掉句号后的长度就不是 19 的倍数。
            # （块长可能因分隔符保留策略偏差 ±1，但句子完整性不变）
            assert len(content.replace("。", "")) % 19 == 0

    def test_chunk_size_respected(self):
        """所有块都不超过 chunk_size"""
        sentence = "这是第一句话。这是第二句话。" * 50  # 约 600 字符
        doc = Document(page_content=sentence)

        chunks = Chunkers.recursive_character([doc], chunk_size=100, overlap=0)
        for chunk in chunks:
            assert len(chunk.page_content) <= 100

    def test_metadata_preserved(self):
        """分块后 metadata 被保留（来源信息不丢失）"""
        doc = Document(
            page_content="内容。" * 100,
            metadata={"source": "policy.pdf", "page": 3},
        )
        chunks = Chunkers.recursive_character([doc], chunk_size=100, overlap=0)
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.metadata["source"] == "policy.pdf"
            assert chunk.metadata["page"] == 3


# ═══════════════ Markdown 分块测试 ═══════════════


MARKDOWN_DOC = """# 安装指南

安装本软件需要以下步骤。

## 依赖

需要 Python 3.10+ 和 pip。

```python
# 这不是标题，是代码注释
x = 1
```

## 配置

编辑 config.yaml 文件。
"""


class TestMarkdownChunker:
    def test_split_by_headers(self):
        """按标题切分：3 个 section（安装指南/依赖/配置）"""
        doc = Document(page_content=MARKDOWN_DOC)
        chunks = Chunkers.markdown([doc])

        # 收集所有块的完整文本
        all_text = "\n".join(c.page_content for c in chunks)
        assert "安装指南" in all_text
        assert "依赖" in all_text
        assert "配置" in all_text

    def test_heading_path_context(self):
        """标题路径上下文："安装指南 > 依赖" 前置到正文"""
        doc = Document(page_content=MARKDOWN_DOC)
        chunks = Chunkers.markdown([doc])

        # 找到含 "Python 3.10" 的块
        dep_chunk = next(c for c in chunks if "Python 3.10" in c.page_content)
        # 验证它带有标题路径前缀
        assert dep_chunk.page_content.startswith("安装指南 > 依赖")

    def test_code_fence_protection(self):
        """代码块保护：代码注释 # 不被切分器打散

        代码块必须完整地出现在某一块中（含 ``` 围栏）。
        """
        doc = Document(page_content=MARKDOWN_DOC)
        chunks = Chunkers.markdown([doc])

        # 找到含代码块的 chunk
        code_chunk = next((c for c in chunks if "x = 1" in c.page_content), None)
        assert code_chunk is not None
        # 代码围栏和注释完整保留
        assert "```python" in code_chunk.page_content
        assert "# 这不是标题，是代码注释" in code_chunk.page_content

    def test_code_comment_not_treated_as_heading(self):
        """代码内的 # 注释不会成为标题（metadata 中不出现）"""
        doc = Document(page_content=MARKDOWN_DOC)
        chunks = Chunkers.markdown([doc])

        # 如果代码注释被误判为标题，metadata 里会出现对应值
        for chunk in chunks:
            for v in chunk.metadata.values():
                assert "不是标题" not in str(v)


# ═══════════════ 掩码/还原辅助函数测试 ═══════════════


class TestCodeFenceMasking:
    def test_mask_and_restore_roundtrip(self):
        """掩码 → 还原：文本完全还原"""
        text = "正文。\n```python\n# 注释\n```\n结尾。"
        masked, fences = _mask_code_fences(text)
        assert len(fences) == 1          # 找到 1 个代码块
        assert "⟦CODEBLOCK0⟧" in masked  # 被替换成占位符
        assert "# 注释" not in masked    # 注释内容不可见

        restored = _restore_code_fences(masked, fences)
        assert restored == text          # 完整还原

    def test_multiple_fences(self):
        """多个代码块：编号递增，各自还原"""
        text = "a```py\nx=1\n```b```js\ny=2\n```c"
        masked, fences = _mask_code_fences(text)
        assert len(fences) == 2
        assert "⟦CODEBLOCK0⟧" in masked
        assert "⟦CODEBLOCK1⟧" in masked
        assert _restore_code_fences(masked, fences) == text

    def test_no_fences_unchanged(self):
        """无代码块：原样返回"""
        text = "普通文本，没有代码。"
        masked, fences = _mask_code_fences(text)
        assert masked == text
        assert fences == []

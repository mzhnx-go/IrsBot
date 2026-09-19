"""文档解析器 — 把各种格式统一转换为 LangChain Document

支持的格式：
- PDF (PyPDFLoader)
- Word docx (Docx2txtLoader)
- 纯文本 / Markdown (TextLoader)
"""

from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document


class DocumentParser:
    """文档解析器

    根据文件扩展名选择对应的 loader，
    统一返回 list[Document]。
    """
    SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}

    @staticmethod
    async def parse(file_path: str) -> list[Document]:
        """根据扩展名自动选择解析器

        Args:
            file_path: 文件路径

        Returns:
            Document 列表（PDF 每页一个 Document）

        Raises:
            ValueError: 不支持的文件格式
            FileNotFoundError: 文件不存在
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        ext = path.suffix.lower()
        if ext not in DocumentParser.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"不支持的文件格式 '{ext},"
                f"支持： {', '.join(sorted(DocumentParser.SUPPORTED_EXTENSIONS))}"
            )
        
        if ext == ".pdf":
            return await DocumentParser.parse_pdf(str(path))
        if ext == ".docx":
            return await DocumentParser.parse_docx(str(path))
        return await DocumentParser.parse_text(str(path))




    @staticmethod
    async def parse_pdf(file_path: str) -> list[Document]:
        """解析 PDF： 每页生成一个 Document"""
        loader = PyPDFLoader(file_path)
        return await loader.aload()

    
    @staticmethod
    async def parse_docx(file_path: str) -> list[Document]:
        """解析 Word docx：整个文件一个 Document"""
        loader = Docx2txtLoader(file_path)
        return await loader.aload()

    @staticmethod
    async def parse_text(file_path: str) -> list[Document]:
        """解析纯文本 / Markdown：整个文件一个 Document"""
        loader = TextLoader(file_path, encoding="utf-8")
        return await loader.aload()



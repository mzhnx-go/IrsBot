"""对话导出渲染层 —— 把会话消息渲染成可下载的文件。

职责边界（单一职责）：
    只做「数据 → 文件字节」的纯转换，不碰数据库、不碰 HTTP。
    归属校验、查询、响应头由路由层（app/api/routes/agent.py）负责。
    这样每种格式都能脱离 FastAPI 直接单测，加新格式也只需在这里加一个渲染函数。

支持格式（ExportFormat）：
    md   Markdown —— 给人看，带标题层级
    txt  纯文本   —— 最朴素，无任何标记符号
    json 结构化   —— 给程序再加工，字段语义明确
    docx Word     —— 可直接交付编辑（python-docx）
    pdf  PDF      —— 只读分发（reportlab）

内容范围（用户已确认）：正文 + 角色 + 时间。
    system / tool 消息不导出 —— 前者是内部系统提示词，后者是工具原始返回，
    都属于「对话链路内部产物」，导出给用户看没有意义（与 WS history 下发口径一致）。

时间口径：
    created_at 在库里是带时区的 UTC，所有格式**按 UTC 原样输出并显式标注**，
    不做本地时区换算 —— 服务端时区不可控（容器默认 UTC），显式标注才不会误读。
"""

import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

# ── 导出格式 ───────────────────────────────────────────────────


class ExportFormat:
    """支持的导出格式标识（与 ?format= 查询参数、前端下拉项一一对应）。"""

    MD = "md"
    TXT = "txt"
    JSON = "json"
    DOCX = "docx"
    PDF = "pdf"

    ALL = (MD, TXT, JSON, DOCX, PDF)

    #: 各格式对应的扩展名（用于拼下载文件名）
    EXTENSION = {
        MD: "md",
        TXT: "txt",
        JSON: "json",
        DOCX: "docx",
        PDF: "pdf",
    }

    #: 各格式的 HTTP Content-Type（带 charset 的必须是 utf-8，
    #: 否则中文在浏览器里会按 latin-1 猜，下载后直接乱码）
    MEDIA_TYPE = {
        MD: "text/markdown; charset=utf-8",
        TXT: "text/plain; charset=utf-8",
        JSON: "application/json; charset=utf-8",
        DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        PDF: "application/pdf",
    }


#: 导出的消息角色白名单 —— 只导出用户可见的对话往返
_EXPORTABLE_ROLES = ("user", "assistant")

#: 角色在导出文件里的显示名
_ROLE_LABEL = {"user": "用户", "assistant": "助手"}


@dataclass(frozen=True)
class ExportedFile:
    """渲染结果：文件名 + 字节内容 + Content-Type。

    路由层拿它直接拼响应头，不需要知道格式细节。
    """

    filename: str
    content: bytes
    media_type: str


# ── 公共小工具 ─────────────────────────────────────────────────


def extract_text(content) -> str:
    """从 Message.content（多态 ContentPart JSON）中取出纯文本。

    content 有三种可能形态：
        dict  → 取 "text" 键（当前落库形态，如 {"text": "你好"}）
        str   → 直接使用（兼容早期直接存字符串的数据）
        其它  → JSON 序列化兜底，保证不抛异常

    参数:
        content: 数据库 Message.content 字段的原始值。

    返回:
        消息正文文本；取不到时返回空字符串。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        text = content.get("text")
        return text if isinstance(text, str) else ""
    return json.dumps(content, ensure_ascii=False) if content else ""


def _format_time(dt: datetime | None, *, iso: bool = False) -> str:
    """把时间戳格式化成导出用的字符串。

    参数:
        dt: 数据库中的时间（预期为带时区的 UTC），可为 None。
        iso: True 返回 ISO 8601（JSON 用，机器可读）；
             False 返回 "YYYY-MM-DD HH:MM:SS UTC"（人读格式）。

    返回:
        格式化后的字符串；dt 为 None 时返回空字符串。
    """
    if dt is None:
        return ""
    if dt.tzinfo is None:
        # 库里约定存 UTC；历史脏数据可能没带时区，按 UTC 补齐而不是猜本地时区
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if iso:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _exportable_messages(messages) -> list:
    """过滤出可导出的消息（只保留 user / assistant）。

    参数:
        messages: Message 对象列表。

    返回:
        过滤后的列表，顺序保持不变。
    """
    return [m for m in messages if m.role in _EXPORTABLE_ROLES]


def _label_of(role: str) -> str:
    """取角色的显示名；未知角色回退为原值。"""
    return _ROLE_LABEL.get(role, role)


_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
#: 文件名主体允许的最大长度（Windows 全路径上限约 260，留足余量给扩展名与重名后缀）
_MAX_FILENAME_STEM = 60


def build_filename(title: str, fmt: str) -> str:
    """根据会话标题与格式拼出安全的下载文件名。

    标题来自用户输入，可能含路径分隔符、控制字符或超长内容，
    直接塞进 Content-Disposition 会造成响应头损坏甚至目录穿越假象，
    这里统一清洗后再拼扩展名。

    参数:
        title: 会话标题。
        fmt: ExportFormat 中的格式标识。

    返回:
        形如 "财务报表分析.pdf" 的文件名。
    """
    stem = _UNSAFE_FILENAME_CHARS.sub("_", (title or "").strip()).strip(" .")
    if not stem:
        stem = "对话"
    stem = stem[:_MAX_FILENAME_STEM].strip() or "对话"
    return f"{stem}.{ExportFormat.EXTENSION[fmt]}"


# ── Markdown ───────────────────────────────────────────────────


def render_markdown(conversation, messages, *, exported_at: datetime) -> str:
    """渲染 Markdown 文本。

    参数:
        conversation: Conversation 对象（用 title / id / created_at）。
        messages: Message 对象列表（时间正序）。
        exported_at: 导出时刻（UTC），写入文首元信息。

    返回:
        Markdown 字符串。
    """
    rows = _exportable_messages(messages)

    lines = [
        f"# {conversation.title}",
        "",
        f"- 会话 ID：`{conversation.id}`",
        f"- 创建时间：{_format_time(conversation.created_at)}",
        f"- 导出时间：{_format_time(exported_at)}",
        f"- 消息条数：{len(rows)}",
        "",
    ]

    if not rows:
        lines += ["---", "", "_（该对话暂无消息）_", ""]
        return "\n".join(lines)

    for m in rows:
        lines += [
            "---",
            "",
            f"## {_label_of(m.role)} · {_format_time(m.created_at)}",
            "",
            extract_text(m.content),
            "",
        ]
    return "\n".join(lines)


# ── 纯文本 ─────────────────────────────────────────────────────


def render_txt(conversation, messages, *, exported_at: datetime) -> str:
    """渲染无标记的纯文本。

    参数与返回同 render_markdown。
    """
    rows = _exportable_messages(messages)

    lines = [
        conversation.title,
        f"创建时间：{_format_time(conversation.created_at)}",
        f"导出时间：{_format_time(exported_at)}",
        f"消息条数：{len(rows)}",
        "=" * 40,
        "",
    ]

    if not rows:
        lines += ["（该对话暂无消息）", ""]
        return "\n".join(lines)

    for m in rows:
        lines += [
            f"[{_label_of(m.role)}] {_format_time(m.created_at)}",
            extract_text(m.content),
            "",
        ]
    return "\n".join(lines)


# ── JSON ───────────────────────────────────────────────────────


def render_json(conversation, messages, *, exported_at: datetime) -> str:
    """渲染结构化 JSON 文本。

    字段全部使用明确语义（不缩写），便于外部脚本直接消费。
    ensure_ascii=False —— 中文原样输出，文件里不该出现 \\uXXXX 转义。

    参数与返回同 render_markdown。
    """
    payload = {
        "conversation": {
            "id": str(conversation.id),
            "title": conversation.title,
            "created_at": _format_time(conversation.created_at, iso=True),
            "updated_at": _format_time(conversation.updated_at, iso=True),
        },
        "exported_at": _format_time(exported_at, iso=True),
        "message_count": len(_exportable_messages(messages)),
        "messages": [
            {
                "role": m.role,
                "content": extract_text(m.content),
                "created_at": _format_time(m.created_at, iso=True),
            }
            for m in _exportable_messages(messages)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ── Word (.docx) ───────────────────────────────────────────────


def render_docx(conversation, messages, *, exported_at: datetime) -> bytes:
    """渲染 Word 文档字节。

    参数与返回同 render_markdown，但返回 bytes。

    实现说明：
        docx 段落里的换行必须写成**软换行**（add_break），
        直接把 "\\n" 塞进段落文本会被 Word 当普通字符吞掉，
        多行回复会挤成一整行。
    """
    from docx import Document
    from docx.shared import Pt

    rows = _exportable_messages(messages)

    doc = Document()
    doc.add_heading(conversation.title, level=1)

    meta = doc.add_paragraph()
    meta.add_run(
        f"创建时间：{_format_time(conversation.created_at)}    "
        f"导出时间：{_format_time(exported_at)}    "
        f"消息条数：{len(rows)}"
    ).font.size = Pt(9)

    if not rows:
        doc.add_paragraph("（该对话暂无消息）")
        return _docx_to_bytes(doc)

    for m in rows:
        head = doc.add_paragraph()
        run = head.add_run(f"{_label_of(m.role)} · {_format_time(m.created_at)}")
        run.bold = True
        run.font.size = Pt(10)

        body = doc.add_paragraph()
        _add_multiline_text(body, extract_text(m.content))

    return _docx_to_bytes(doc)


def _add_multiline_text(paragraph, text: str) -> None:
    """把多行文本写进一个段落，换行用软换行还原。

    参数:
        paragraph: python-docx 的 Paragraph 对象。
        text: 原始文本（可能含 \\n）。
    """
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if index:
            paragraph.add_run().add_break()
        paragraph.add_run(line)


def _docx_to_bytes(doc) -> bytes:
    """把 python-docx 文档对象序列化为字节。

    参数:
        doc: python-docx Document 对象。

    返回:
        .docx 文件的字节内容。
    """
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# ── PDF ────────────────────────────────────────────────────────

#: app 包根目录（本文件在 app/core/agent/ 下，往上三层才是 app/）
_APP_DIR = Path(__file__).resolve().parents[2]

#: 随仓库分发的字体（OFL 1.1，可商用）。放在 app/assets/fonts/ 下，
#: Dockerfile 的 `COPY ./backend/app` 会自动带进镜像，无需额外 COPY。
_PDF_FONT_PATH = _APP_DIR / "assets" / "fonts" / "NotoSansSC-Regular.ttf"

#: 注册到 reportlab 的字体名（自定义名，避免与内置字体撞名）
_PDF_FONT_NAME = "NotoSansSC"

#: 找不到字体文件时的兜底：reportlab 内置的 Adobe 标准中文字体。
#: 它**不嵌入字体**，靠阅读器自带的 CJK 字体渲染 —— 本机缺中文字体的
#: 环境会显示成方框，故仅作兜底，正常路径一定用上面的 TTF。
_PDF_FALLBACK_FONT_NAME = "STSong-Light"


@lru_cache(maxsize=1)
def _pdf_font_name() -> str:
    """注册并返回 PDF 使用的字体名（进程内只注册一次）。

    返回:
        可用字体名：优先随包分发的 Noto Sans SC，缺失时退回 STSong-Light。
    """
    from reportlab.pdfbase import pdfmetrics

    if _PDF_FONT_PATH.is_file():
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont(_PDF_FONT_NAME, str(_PDF_FONT_PATH)))
        return _PDF_FONT_NAME

    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont(_PDF_FALLBACK_FONT_NAME))
    return _PDF_FALLBACK_FONT_NAME


def render_pdf(conversation, messages, *, exported_at: datetime) -> bytes:
    """渲染 PDF 文档字节。

    参数与返回同 render_markdown，但返回 bytes。

    实现说明：
        用 platypus（高层排版）而非 canvas（手算坐标）—— 对话长度不可预知，
        需要在页码处自动分页并保证段落不断行错位。
        wordWrap="CJK" 必须显式指定：默认按空格断行，中文整段没有空格，
        会被当成一个超长单词直接冲出页面右边。
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font = _pdf_font_name()
    rows = _exportable_messages(messages)

    title_style = ParagraphStyle(
        "Title", fontName=font, fontSize=16, leading=24, wordWrap="CJK"
    )
    meta_style = ParagraphStyle(
        "Meta",
        fontName=font,
        fontSize=8.5,
        leading=14,
        textColor=colors.HexColor("#666666"),
        wordWrap="CJK",
    )
    role_style = ParagraphStyle(
        "Role",
        fontName=font,
        fontSize=11,
        leading=18,
        textColor=colors.HexColor("#1f6feb"),
        spaceBefore=6,
        wordWrap="CJK",
    )
    body_style = ParagraphStyle(
        "Body", fontName=font, fontSize=10.5, leading=17, wordWrap="CJK"
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=conversation.title,
        author="IrsBot",
    )

    story = [
        Paragraph(_escape_pdf(conversation.title), title_style),
        Spacer(1, 4),
        Paragraph(
            _escape_pdf(
                f"创建时间：{_format_time(conversation.created_at)}　"
                f"导出时间：{_format_time(exported_at)}　"
                f"消息条数：{len(rows)}"
            ),
            meta_style,
        ),
        Spacer(1, 6),
    ]

    if not rows:
        story.append(Paragraph("（该对话暂无消息）", body_style))
    else:
        for m in rows:
            story.append(
                Paragraph(
                    _escape_pdf(
                        f"{_label_of(m.role)} · {_format_time(m.created_at)}"
                    ),
                    role_style,
                )
            )
            # 正文按段落切分：Paragraph 不认 "\n"，必须显式换成 <br/>
            text = _escape_pdf(extract_text(m.content)).replace("\n", "<br/>")
            story.append(Paragraph(text or "&nbsp;", body_style))

    doc.build(story)
    return buffer.getvalue()


def _escape_pdf(text: str) -> str:
    """转义 reportlab 段落里的 markup 特殊字符。

    Paragraph 接受的是迷你 HTML 子集，正文里的 & < > 若不转义，
    轻则丢字符、重则解析失败抛异常（例如用户问过 "<div> 怎么写"）。

    参数:
        text: 原始文本。

    返回:
        转义后的文本。
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── 统一入口 ───────────────────────────────────────────────────


def render_export(
    conversation, messages, fmt: str, *, exported_at: datetime | None = None
) -> ExportedFile:
    """按格式渲染导出文件（本模块唯一对外入口）。

    参数:
        conversation: Conversation 对象。
        messages: Message 对象列表（时间正序）。
        fmt: ExportFormat 中的格式标识。
        exported_at: 导出时刻；默认取当前 UTC 时间。

    返回:
        ExportedFile（文件名 / 字节内容 / Content-Type）。

    异常:
        ValueError: fmt 不在 ExportFormat.ALL 中。
    """
    if fmt not in ExportFormat.ALL:
        raise ValueError(f"不支持的导出格式：{fmt}")

    if exported_at is None:
        exported_at = datetime.now(timezone.utc)

    if fmt == ExportFormat.MD:
        content = render_markdown(
            conversation, messages, exported_at=exported_at
        ).encode("utf-8")
    elif fmt == ExportFormat.TXT:
        content = render_txt(
            conversation, messages, exported_at=exported_at
        ).encode("utf-8")
    elif fmt == ExportFormat.JSON:
        content = render_json(
            conversation, messages, exported_at=exported_at
        ).encode("utf-8")
    elif fmt == ExportFormat.DOCX:
        content = render_docx(conversation, messages, exported_at=exported_at)
    else:
        content = render_pdf(conversation, messages, exported_at=exported_at)

    return ExportedFile(
        filename=build_filename(conversation.title, fmt),
        content=content,
        media_type=ExportFormat.MEDIA_TYPE[fmt],
    )
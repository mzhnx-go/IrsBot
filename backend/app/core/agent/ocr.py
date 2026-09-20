"""本地 OCR 回退 —— 模型不支持视觉时，用离线 OCR 引擎把图中文字提出来。

为什么自己跑 OCR（而不是让用户再配一个视觉模型源）：
用户要的是「开箱可用」——没配第二个模型源时，图片不能变成一句
「看不了」。rapidocr + onnxruntime 是纯离线方案，模型随 wheel 一起分发，
运行期不联网。

设计要点：
- **懒加载 + 进程内单例**：onnxruntime 会话初始化有成本（首次约 0.4s，
  加载 3 个 onnx 模型），但只在真的遇到「非视觉模型 + 图片」时才付这个钱。
- **缺失即降级**：rapidocr 没装（或平台不支持）时 `is_available()` 返回
  False，上层退回到「无法查看图片内容」的中文提示，绝不抛异常打断整轮对话。
- **同步推理丢线程池**：OCR 是 CPU 密集且单张约 1-2s，直接在事件循环里跑
  会卡住整个 worker；用 `asyncio.to_thread` + 进程内锁串行化。
- **只提文字，不留结果**：识别产物只进本轮上下文，不落库（与文档附件同策略）。
"""

import asyncio
import importlib.util
import logging
import threading
import uuid
from pathlib import Path

from app.core.agent import attachments as _attachments
from app.core.config import settings

logger = logging.getLogger(__name__)

_engine_lock = threading.Lock()
_engine: object | None = None
_engine_failed = False


def is_available() -> bool:
    """OCR 引擎依赖是否已安装（不真正初始化，避免导入期付加载成本）。"""
    return importlib.util.find_spec("rapidocr") is not None


def _get_engine() -> object | None:
    """取进程内共享的 OCR 引擎；不可用或初始化失败返回 None。

    失败后记住 `_engine_failed`：一次初始化失败通常是缺模型/缺系统库，
    重试没有意义，但每次对话都重试一次会持续拖慢响应。
    """
    global _engine, _engine_failed
    if _engine is not None or _engine_failed:
        return _engine
    with _engine_lock:
        if _engine is not None or _engine_failed:
            return _engine
        try:
            from rapidocr import RapidOCR

            _engine = RapidOCR()
            logger.info("本地 OCR 引擎已就绪")
        except Exception:
            _engine_failed = True
            logger.exception("本地 OCR 引擎初始化失败，将退回到纯文本提示")
        return _engine


def recognize(path: Path) -> str:
    """对单张图片做 OCR，返回识别出的文字（可能为空）。"""
    engine = _get_engine()
    if engine is None:
        return ""
    try:
        result = engine(str(path))  # type: ignore[operator]
    except Exception:
        logger.exception("OCR 识别失败: %s", path.name)
        return ""
    # rapidocr 3.x 返回带 txts 的结果对象；无文字时为 None
    texts = getattr(result, "txts", None) or ()
    return "\n".join(str(t) for t in texts if t)


async def _recognize_async(path: Path) -> str:
    """在单独的线程里跑 OCR（单张 1-2s，不能占用事件循环）。"""
    return await asyncio.to_thread(recognize, path)


async def build_image_context(
    meta: list[dict],
    *,
    user_id: uuid.UUID | str,
    conversation_id: uuid.UUID | str,
) -> str:
    """把图片附件经 OCR 识别成文本块（供非视觉模型使用）。

    Returns:
        拼好的文本块；没有图片、引擎不可用、或全部识别为空时返回空串。
    """
    images = [m for m in meta if m.get("kind") == _attachments.KIND_IMAGE]
    if not images or not is_available():
        return ""

    limit = settings.OCR_MAX_CHARS
    blocks: list[str] = []
    for item in images:
        att_id = str(item.get("id") or "")
        filename = str(item.get("filename") or "图片")
        path = _attachments.resolve(
            user_id=user_id, conversation_id=conversation_id, att_id=att_id
        )
        if path is None:
            continue
        text = (await _recognize_async(path)).strip()
        if not text:
            continue
        if len(text) > limit:
            text = text[:limit] + "\n（识别文字过长已截断）"
        blocks.append(f"【图片 OCR：{filename}】\n{text}")
    return "\n\n".join(blocks)

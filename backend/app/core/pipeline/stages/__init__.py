"""Pipeline stages package — 对外暴露所有内置 Stage.

标准流水线组装顺序（Phase 12.1 决策表，权威顺序）:
    RateLimitStage → SessionStatusStage → PreProcessStage
    → ProcessStage → PostProcessStage

裁剪结论：WakingCheck / WhitelistCheck（群聊场景）不做；
Whitelist 的职责由路由层会话归属校验（ResourceOwnerCheck）承担；
ContentSafety 可选暂不实现；洋葱模型经决策保持顺序模型。
"""

from app.core.pipeline.stages.post_process import PostProcessStage
from app.core.pipeline.stages.pre_process import PreProcessStage
from app.core.pipeline.stages.process import ProcessStage
from app.core.pipeline.stages.rate_limit import RateLimitStage, get_rate_limit_stage
from app.core.pipeline.stages.session_status import SessionStatusStage

#: 权威 Stage 顺序。REST 与 WS 的前置 Stage 组装都必须遵循此顺序。
STAGES_ORDER: list[str] = [
    "rate_limit",
    "session_status",
    "pre_process",
    "process",
    "post_process",
]

__all__ = [
    "STAGES_ORDER",
    "PostProcessStage",
    "PreProcessStage",
    "ProcessStage",
    "RateLimitStage",
    "SessionStatusStage",
    "get_rate_limit_stage",
]

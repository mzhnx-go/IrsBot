"""视觉能力判定单测（Phase 16 / S5）。

判定优先级：ProviderConfig.supports_vision 显式值 > 模型名启发式。
「显式可纠正、自动有默认」是这块的全部价值，两条路径都要钉住。
"""

from types import SimpleNamespace

import pytest

from app.core.agent.provider import (
    looks_like_vision_model,
    resolve_supports_vision,
)


class TestLooksLikeVisionModel:
    @pytest.mark.parametrize(
        "name",
        [
            "qwen-vl-max",
            "qwen2.5-vl-72b-instruct",
            "gpt-4o",
            "gpt-4o-mini",
            "claude-3-5-sonnet-20241022",
            "gemini-2.0-flash",
            "glm-4v-plus",
            "qvq-72b-preview",
            "internvl2-8b",
            "MiniCPM-V-2_6",
            "llava-1.5-7b",
            "gpt-5-vision",
            "some-omni-model",
            "MULTIMODAL-1",  # 大小写无关
        ],
    )
    def test_recognizes_vision_models(self, name: str):
        assert looks_like_vision_model(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "gpt-3.5-turbo",
            "qwen3.8-flash",
            "agnes-3.0-flash",
            "deepseek-chat",
            "claude-2.1",
            "text-embedding-3-small",
            "",
        ],
    )
    def test_rejects_text_only_models(self, name: str):
        assert looks_like_vision_model(name) is False

    def test_handles_none(self):
        assert looks_like_vision_model(None) is False


class TestResolveSupportsVision:
    def test_explicit_true_wins_over_name(self):
        """显式标记是可纠正的出口：名字不像视觉模型也认"""
        pc = SimpleNamespace(supports_vision=True, model_name="qwen3.8-flash")
        assert resolve_supports_vision(pc) is True

    def test_explicit_false_wins_over_name(self):
        """名字里带 vl 但用户声明不支持（比如中转站阉割了图片）"""
        pc = SimpleNamespace(supports_vision=False, model_name="qwen-vl-max")
        assert resolve_supports_vision(pc) is False

    def test_auto_falls_back_to_name_heuristic(self):
        pc = SimpleNamespace(supports_vision=None, model_name="qwen-vl-max")
        assert resolve_supports_vision(pc) is True
        pc2 = SimpleNamespace(supports_vision=None, model_name="qwen3.8-flash")
        assert resolve_supports_vision(pc2) is False

    def test_call_argument_model_name_beats_config(self):
        """Agent 可临时指定模型：判定要用本次实际使用的那个"""
        pc = SimpleNamespace(supports_vision=None, model_name="qwen3.8-flash")
        assert resolve_supports_vision(pc, model_name="gpt-4o") is True

    def test_none_config_uses_name_only(self):
        assert resolve_supports_vision(None, model_name="gpt-4o") is True
        assert resolve_supports_vision(None, model_name="deepseek-chat") is False
        assert resolve_supports_vision(None) is False

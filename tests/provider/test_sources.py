"""Tests for model sources configuration."""

from app.core.agent.provider import (
    MODEL_SOURCES,
    get_default_model,
    get_model_capabilities,
    get_supported_models,
)


class TestModelSources:
    def test_all_providers_defined(self):
        assert "openai" in MODEL_SOURCES
        assert "anthropic" in MODEL_SOURCES
        assert "gemini" in MODEL_SOURCES

    def test_openai_has_default_model(self):
        assert MODEL_SOURCES["openai"]["default_model"] == "gpt-4o"

    def test_anthropic_has_default_model(self):
        assert MODEL_SOURCES["anthropic"]["default_model"] == "claude-3-5-sonnet-20241022"

    def test_gemini_has_default_model(self):
        assert MODEL_SOURCES["gemini"]["default_model"] == "gemini-2.0-flash"


class TestGetSupportedModels:
    def test_openai_models(self):
        models = get_supported_models("openai")
        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models

    def test_unknown_provider(self):
        assert get_supported_models("unknown") == []


class TestGetDefaultModel:
    def test_known_provider(self):
        assert get_default_model("openai") == "gpt-4o"
        assert get_default_model("anthropic") == "claude-3-5-sonnet-20241022"

    def test_unknown_provider(self):
        assert get_default_model("unknown") is None


class TestGetModelCapabilities:
    def test_openai_gpt4o(self):
        caps = get_model_capabilities("openai", "gpt-4o")
        assert caps is not None
        assert caps["supports_tools"] is True
        assert caps["supports_image"] is True
        assert caps["supports_stream"] is True
        assert caps["max_tokens"] == 128000

    def test_unknown_model(self):
        assert get_model_capabilities("openai", "nonexistent") is None

    def test_unknown_provider(self):
        assert get_model_capabilities("unknown", "gpt-4o") is None

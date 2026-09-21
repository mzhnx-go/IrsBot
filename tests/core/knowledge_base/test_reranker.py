"""Reranker 重排段单元测试 — 全部 mock httpx，不发真实请求。"""

from unittest.mock import patch

import httpx
import pytest
from app.core.config import settings
from app.core.knowledge_base import reranker
from app.core.knowledge_base.reranker import rerank
from langchain_core.documents import Document


@pytest.fixture(autouse=True)
def enable_rerank(monkeypatch):
    """统一打开开关并保证有 Key，个别用例再单独覆盖"""
    monkeypatch.setattr(settings, "ENABLE_RERANK", True)
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(
        settings, "EMBEDDING_BASE_URL", "https://fake.example.com/v1", raising=False
    )


DOCS = [
    Document("A 相关内容"),
    Document("B 不相关内容"),
    Document("C 高相关内容"),
]


def _patch_post(json_body, raise_exc=None):
    """构造 mock 的 httpx.post，返回 (patcher, 调用记录容器)"""
    calls = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return json_body

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        if raise_exc:
            raise raise_exc
        return FakeResponse()

    return patch.object(httpx, "post", side_effect=fake_post), calls


def test_rerank_orders_by_relevance_score():
    """按 API 返回的 relevance_score 顺序重排"""
    p, calls = _patch_post({"results": [
        {"index": 2, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.5},
    ]})
    with p:
        result = rerank("查询", DOCS, top_n=2)
    assert [d.page_content for d in result] == ["C 高相关内容", "A 相关内容"]
    # 请求体形状：Jina 协议 + Bearer 头
    body = calls["kwargs"]["json"]
    assert body["model"] == settings.RERANK_MODEL
    assert body["documents"] == [d.page_content for d in DOCS]
    assert calls["kwargs"]["headers"]["Authorization"] == "Bearer test-key"
    assert "/rerank" in calls["url"]


def test_rerank_api_error_falls_back_to_original_order():
    """API 抛异常 → 降级为原序截断，绝不向外抛错"""
    p, _ = _patch_post(None, raise_exc=httpx.ConnectError("network down"))
    with p:
        result = rerank("查询", DOCS, top_n=2)
    assert [d.page_content for d in result] == ["A 相关内容", "B 不相关内容"]


def test_rerank_disabled_skips_request():
    """开关关闭 → 不发请求，直接原序截断"""
    p, calls = _patch_post({"results": [{"index": 0, "relevance_score": 1.0}]})
    with p, patch.object(settings, "ENABLE_RERANK", False):
        result = rerank("查询", DOCS, top_n=1)
    assert calls == {}  # 未发出任何 HTTP 请求
    assert [d.page_content for d in result] == ["A 相关内容"]


def test_rerank_empty_result_falls_back():
    """API 返回空 results → 降级为原序截断"""
    p, _ = _patch_post({"results": []})
    with p:
        assert rerank("查询", DOCS, top_n=2) == DOCS[:2]


def test_rerank_no_docs_short_circuits():
    """空候选直接返回空，不发请求"""
    p, calls = _patch_post({"results": []})
    with p:
        assert rerank("查询", [], top_n=2) == []
    assert calls == {}


def test_rerank_module_uses_settings_candidate_constant():
    """RERANK_CANDIDATES 配置存在且为正，供 HybridRetriever 截断候选"""
    assert settings.RERANK_CANDIDATES >= 1
    assert reranker._RERANK_TIMEOUT_SECONDS == 5.0


# ---------- P9a：显式端点（用户配的 rerank 模型源） ----------


def test_rerank_explicit_endpoint_wins_over_env_and_switch():
    """传了 endpoint 就用它：请求打向该源的 Key / 地址 / 模型"""
    from app.core.knowledge_base.endpoints import RerankEndpoint

    ep = RerankEndpoint(
        api_key="sk-provider-key",
        base_url="https://rr.example.com/v1",
        model="BAAI/bge-reranker-v2-m3",
    )
    p, calls = _patch_post({"results": [{"index": 2, "relevance_score": 0.9}]})
    with p, patch.object(settings, "ENABLE_RERANK", False):
        result = rerank("查询", DOCS, top_n=1, endpoint=ep)

    assert [d.page_content for d in result] == ["C 高相关内容"]
    assert calls["url"].startswith("https://rr.example.com/v1/rerank")
    assert calls["kwargs"]["headers"]["Authorization"] == "Bearer sk-provider-key"
    assert calls["kwargs"]["json"]["model"] == "BAAI/bge-reranker-v2-m3"


def test_rerank_explicit_endpoint_still_degrades_on_error():
    """端点显式传入时同样降级——上游挂了不能把检索打挂"""
    from app.core.knowledge_base.endpoints import RerankEndpoint

    ep = RerankEndpoint(
        api_key="sk-k", base_url="https://rr.example.com/v1", model="m"
    )
    p, _ = _patch_post(None, raise_exc=httpx.ConnectError("network down"))
    with p:
        assert rerank("查询", DOCS, top_n=2, endpoint=ep) == DOCS[:2]


def test_hybrid_retriever_passes_endpoint_to_rerank():
    """检索器把构造期解析好的端点原样交给 rerank（P9a 接线点）"""
    from app.core.knowledge_base.endpoints import RerankEndpoint
    from app.core.knowledge_base import retrieval

    class FakeStore:
        def search(self, query, top_k):
            return [Document("向量命中")]

    ep = RerankEndpoint(api_key="k", base_url="https://rr/v1", model="m")
    retriever = retrieval.HybridRetriever(
        FakeStore(), [Document("语料")], rerank_endpoint=ep
    )
    seen = {}

    def fake_rerank(query, docs, top_n, endpoint=None):
        seen["endpoint"] = endpoint
        return docs[:top_n]

    with patch.object(retrieval, "rerank", side_effect=fake_rerank):
        retriever.retrieve("查询", top_k=1)

    assert seen["endpoint"] == ep

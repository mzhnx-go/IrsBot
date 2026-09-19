"""_LRUCache 单元测试：容量淘汰与命中刷新（provider.py 随手修）。"""

from app.core.agent.provider import _LRUCache


def test_lru_evicts_oldest_when_over_capacity():
    cache = _LRUCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2
    cache["c"] = 3  # 容量超限，应淘汰最久未用的 a
    assert "a" not in cache
    assert cache["b"] == 2 and cache["c"] == 3


def test_lru_hit_refreshes_recency():
    cache = _LRUCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2
    assert cache.get_hit("a") == 1  # 访问 a，使 b 变成最久未用
    cache["c"] = 3  # 应淘汰 b 而不是 a
    assert "b" not in cache
    assert cache.get_hit("a") == 1


def test_lru_get_hit_miss_returns_none():
    cache = _LRUCache()
    assert cache.get_hit("missing") is None


def test_lru_reinsert_moves_to_end():
    cache = _LRUCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2
    cache["a"] = 10  # 重新赋值也算「最近使用」
    cache["c"] = 3  # 淘汰 b
    assert cache.get_hit("a") == 10
    assert "b" not in cache

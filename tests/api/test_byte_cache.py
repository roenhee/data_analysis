"""ByteBudgetCache: 엔트리 개수가 아니라 바이트 예산으로 evict 한다.

path 큐브(하루 ~245MB)를 실측한 뒤 넣은 안전장치 — functools.lru_cache(maxsize=8) 는
개수 기준이라 31일 path 8벌이면 ~61GB 로 OOM 이다. 여기서는 각 값의 바이트를 재서
예산을 넘으면 가장 오래 안 쓴 것부터 버린다.
"""
import collections

from api.byte_cache import ByteBudgetCache


class _Obj:
    """크기를 스스로 아는 가짜 캐시 값 — 실제 큐브 없이 바이트 회계를 검증한다."""
    def __init__(self, key: str, size: int):
        self.key = key
        self.size = size


def _counting_loader(calls: collections.Counter, key: str, size: int):
    def load() -> _Obj:
        calls[key] += 1
        return _Obj(key, size)
    return load


def test_hit_returns_same_object_without_reloading():
    calls: collections.Counter = collections.Counter()
    cache = ByteBudgetCache(budget_bytes=1000, sizeof=lambda o: o.size)
    a = cache.get_or_load("a", _counting_loader(calls, "a", 100))
    again = cache.get_or_load("a", _counting_loader(calls, "a", 100))
    assert again is a
    assert calls["a"] == 1


def test_evicts_least_recently_used_when_over_budget():
    calls: collections.Counter = collections.Counter()
    cache = ByteBudgetCache(budget_bytes=100, sizeof=lambda o: o.size)
    cache.get_or_load("a", _counting_loader(calls, "a", 60))  # total 60
    cache.get_or_load("b", _counting_loader(calls, "b", 60))  # 120>100 → evict a
    # a 는 쫓겨났으므로 다시 부르면 loader 가 또 돈다(그리고 이번엔 b 가 쫓겨난다).
    cache.get_or_load("a", _counting_loader(calls, "a", 60))
    assert calls["a"] == 2
    assert calls["b"] == 1


def test_recent_access_protects_from_eviction():
    calls: collections.Counter = collections.Counter()
    cache = ByteBudgetCache(budget_bytes=100, sizeof=lambda o: o.size)
    cache.get_or_load("a", _counting_loader(calls, "a", 40))
    cache.get_or_load("b", _counting_loader(calls, "b", 40))  # total 80
    cache.get_or_load("a", _counting_loader(calls, "a", 40))  # 히트 → a 가 최신
    cache.get_or_load("c", _counting_loader(calls, "c", 40))  # 120>100 → LRU=b evict
    # b 가 쫓겨났으므로 재로드, a 는 남아 히트.
    cache.get_or_load("a", _counting_loader(calls, "a", 40))
    cache.get_or_load("b", _counting_loader(calls, "b", 40))
    assert calls["a"] == 1
    assert calls["b"] == 2
    assert calls["c"] == 1


def test_single_entry_over_budget_is_still_served_and_cached():
    calls: collections.Counter = collections.Counter()
    cache = ByteBudgetCache(budget_bytes=100, sizeof=lambda o: o.size)
    big = cache.get_or_load("big", _counting_loader(calls, "big", 500))  # 예산 초과
    assert big is not None
    again = cache.get_or_load("big", _counting_loader(calls, "big", 500))
    assert again is big  # 자기 자신은 쫓아내지 않는다 — 그렇지 않으면 매번 재로드
    assert calls["big"] == 1


def test_nbytes_tracks_current_total():
    cache = ByteBudgetCache(budget_bytes=100, sizeof=lambda o: o.size)
    assert cache.nbytes == 0
    cache.get_or_load("a", lambda: _Obj("a", 40))
    assert cache.nbytes == 40
    cache.get_or_load("b", lambda: _Obj("b", 40))
    assert cache.nbytes == 80
    cache.get_or_load("c", lambda: _Obj("c", 40))  # 120>100 → evict a → 80
    assert cache.nbytes == 80

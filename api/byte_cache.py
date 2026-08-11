"""바이트 예산 기반 LRU 캐시.

`functools.lru_cache(maxsize=N)` 는 **엔트리 개수**로만 자른다. 값 크기가 제각각이면
(세션 큐브 ~2MB vs 31일 path 큐브 ~7.6GB) 개수 상한은 메모리를 지키지 못한다 — path
분석을 붙이면 8벌이 ~61GB 로 36GB RAM 을 넘겨 OOM 이다. 여기서는 삽입 때 값의 바이트를
재서 **총합이 예산을 넘으면 가장 오래 안 쓴 것부터** 버린다.

self-eviction 은 하지 않는다: 값 하나가 예산보다 커도 그건 지금 요청이 필요로 하는
값이라 내주고 캐시에 남긴다(안 그러면 매 조회마다 재로드한다). 예산은 정상 흐름의 누적을
막는 장치지, 단일 거대 조회의 최후 방어선이 아니다 — 그건 기간 상한(HARD_LIMIT_DAYS)이 한다.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class ByteBudgetCache(Generic[K, V]):
    def __init__(self, budget_bytes: int, sizeof: Callable[[V], int]):
        self._budget = budget_bytes
        self._sizeof = sizeof
        self._store: OrderedDict[K, tuple[V, int]] = OrderedDict()
        self._total = 0
        self._lock = threading.Lock()

    @property
    def nbytes(self) -> int:
        return self._total

    def get_or_load(self, key: K, loader: Callable[[], V]) -> V:
        with self._lock:
            hit = self._store.get(key)
            if hit is not None:
                self._store.move_to_end(key)
                return hit[0]
        # 로드는 느리다(파케이 수백 MB) — 락을 쥔 채 하면 다른 키 조회까지 멈춘다.
        # 락 밖에서 로드하고 다시 확인한다(동시 중복 로드는 재확인으로 흡수).
        value = loader()
        size = self._sizeof(value)
        with self._lock:
            hit = self._store.get(key)
            if hit is not None:  # 그새 다른 스레드가 채웠다 — 그 값을 쓴다(중복 폐기).
                self._store.move_to_end(key)
                return hit[0]
            self._store[key] = (value, size)
            self._total += size
            self._evict_locked()
            return value

    def _evict_locked(self) -> None:
        # 예산 초과분을 LRU(앞쪽)부터 버린다. 방금 넣은 것(맨 뒤)은 self-eviction 하지
        # 않으므로 len>1 가드를 둔다.
        while self._total > self._budget and len(self._store) > 1:
            _, (_, size) = self._store.popitem(last=False)
            self._total -= size

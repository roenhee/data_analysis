"""큐브 로드 + LRU 캐시 + 기간 상한. analyses/ 는 건드리지 않는다.

날짜 파티션 parquet 를 **선택 기간만** 읽어(load_cube_set 이 요청 날짜만 로드) lru_cache 로
프로세스에 공유한다 — 동시 사용자가 늘어도 큐브는 한 벌이라 메모리가 일정하다(읽기 전용 공유).
소프트 상한(31일)은 막지 않고 경고(analysis.py 가 envelope 에 싣는다), 절대 상한(90일)은
거부한다(경고를 무시한 거대 조회의 OOM 최후 방어선).
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from analytics.analyses.base import CubeSet
from analytics.analyses.cubes import load_cube_set
from api.byte_cache import ByteBudgetCache
from dashboard.filters import expand_dates  # 순수 함수 재사용(st 의존 없음)
from data_layer.config import Config

SOFT_LIMIT_DAYS = 31   # 초과 시 경고(막지 않음)
HARD_LIMIT_DAYS = 90   # 초과 시 거부(OOM 방어)

# 캐시 바이트 예산. path 큐브는 실측 ~245MB/일이라 31일이면 한 벌 ~7.6GB — 개수 기준
# 캐시(옛 maxsize=8)는 8벌 ~61GB 로 36GB RAM 을 넘긴다. 16GiB 예산이면 큰 path 조회 두
# 벌 정도를 담고 분석 연산·OS 에 여유를 남긴다. session 전용 조회는 ~2MB 라 사실상 무제한.
# (단일 초거대 조회의 OOM 은 예산이 아니라 HARD_LIMIT_DAYS 가 막는다 — 예산은 누적 방어다.)
CACHE_BUDGET_BYTES = 16 * 1024**3


class PeriodTooLongError(ValueError):
    """절대 상한을 넘는 기간 요청. 라우터가 400 으로 매핑한다."""


def period_days(start: str, end: str) -> int:
    """[start, end] 양끝 포함 일수."""
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def _cubeset_bytes(cs: CubeSet) -> int:
    """CubeSet 이 실제로 쥔 pandas 메모리(있는 프레임의 deep 합)."""
    total = 0
    for name in ("session", "transition", "quality",
                 "action", "cond_transition", "path"):
        frame = getattr(cs, name)
        if frame is not None:
            total += int(frame.memory_usage(deep=True).sum())
    return total


_CACHE: ByteBudgetCache[tuple, CubeSet] = ByteBudgetCache(
    budget_bytes=CACHE_BUDGET_BYTES, sizeof=_cubeset_bytes
)


def _load_cached(
    cube_names: tuple[str, ...], start: str, end: str,
    services: tuple[str, ...], state_dict_version: str,
) -> CubeSet:
    """실제 로드. 인자 튜플이 캐시 키다. 바이트 예산으로 evict 한다(개수 아님)."""
    key = (cube_names, start, end, services, state_dict_version)
    return _CACHE.get_or_load(
        key,
        lambda: load_cube_set(
            Config.from_env(),
            dates=expand_dates([start, end]),
            services=list(services),
            state_dict_version=state_dict_version,
            cube_names=cube_names,
        ),
    )


def load(
    cube_names: Iterable[str], start: str, end: str,
    services: Iterable[str], state_dict_version: str,
) -> CubeSet:
    """기간 상한을 검사하고 캐시된 로드를 부른다."""
    days = period_days(start, end)
    if days < 1:
        raise ValueError(
            f"start({start}) 가 end({end}) 보다 이후입니다 — start 는 end 이전이거나 "
            "같아야 합니다."
        )
    if days > HARD_LIMIT_DAYS:
        raise PeriodTooLongError(
            f"기간 {days}일이 절대 상한 {HARD_LIMIT_DAYS}일을 넘습니다 — "
            "메모리 보호를 위해 좁혀서 조회하세요."
        )
    return _load_cached(
        tuple(cube_names), start, end, tuple(services), state_dict_version
    )

"""큐브 로드 + LRU 캐시 + 기간 상한. analyses/ 는 건드리지 않는다.

날짜 파티션 parquet 를 **선택 기간만** 읽어(load_cube_set 이 요청 날짜만 로드) lru_cache 로
프로세스에 공유한다 — 동시 사용자가 늘어도 큐브는 한 벌이라 메모리가 일정하다(읽기 전용 공유).
소프트 상한(31일)은 막지 않고 경고(analysis.py 가 envelope 에 싣는다), 절대 상한(90일)은
거부한다(경고를 무시한 거대 조회의 OOM 최후 방어선).
"""
from __future__ import annotations

import functools
from datetime import date

from analytics.analyses.base import CubeSet
from analytics.analyses.cubes import load_cube_set
from dashboard.filters import expand_dates  # 순수 함수 재사용(st 의존 없음)
from data_layer.config import Config

SOFT_LIMIT_DAYS = 31   # 초과 시 경고(막지 않음)
HARD_LIMIT_DAYS = 90   # 초과 시 거부(OOM 방어)


class PeriodTooLongError(ValueError):
    """절대 상한을 넘는 기간 요청. 라우터가 400 으로 매핑한다."""


def period_days(start: str, end: str) -> int:
    """[start, end] 양끝 포함 일수."""
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


@functools.lru_cache(maxsize=8)
def _load_cached(
    cube_names: tuple[str, ...], start: str, end: str,
    services: tuple[str, ...], state_dict_version: str,
) -> CubeSet:
    """실제 로드. 인자가 전부 해시 가능(튜플·문자열)이라 lru_cache 키가 된다."""
    return load_cube_set(
        Config.from_env(),
        dates=expand_dates([start, end]),
        services=list(services),
        state_dict_version=state_dict_version,
        cube_names=cube_names,
    )


def load(
    cube_names, start: str, end: str, services, state_dict_version: str,
) -> CubeSet:
    """기간 상한을 검사하고 캐시된 로드를 부른다."""
    days = period_days(start, end)
    if days > HARD_LIMIT_DAYS:
        raise PeriodTooLongError(
            f"기간 {days}일이 절대 상한 {HARD_LIMIT_DAYS}일을 넘습니다 — "
            "메모리 보호를 위해 좁혀서 조회하세요."
        )
    return _load_cached(
        tuple(cube_names), start, end, tuple(services), state_dict_version
    )

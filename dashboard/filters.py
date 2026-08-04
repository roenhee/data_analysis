"""세그먼트 dict → CubeSet. load_cube_set 위의 얇은 배선."""
from __future__ import annotations

from analytics.analyses.base import CubeSet
from analytics.analyses.cubes import (
    ALL_CUBE_NAMES,
    DEFAULT_CUBE_NAMES,
    load_cube_set,
)
from data_layer.config import Config

# path·action·cond_transition 을 쓰는 분석. markov 는 transition 도 쓰므로 전부 싣는다.
ACTION_ANALYSES = frozenset(
    {"click_distribution", "conditional_flow", "path_ranking", "markov_order_test"}
)

# app.py 가 사이드바 위젯으로 채우는 축들.
SEGMENT_AXES = ("service_type", "app_version", "os", "gender", "age_band", "daypart")


def cube_names_for(analysis: str) -> tuple[str, ...]:
    """분석이 필요로 하는 큐브 목록. 행동층이면 전부, 아니면 화면층 셋."""
    return ALL_CUBE_NAMES if analysis in ACTION_ANALYSES else DEFAULT_CUBE_NAMES


def apply_segment(cubes: CubeSet, segment: dict) -> CubeSet:
    """값이 채워진 축만 `cubes.filter` 로 좁힌다. 빈 문자열 축은 건너뛴다."""
    active = {a: segment[a] for a in SEGMENT_AXES if segment.get(a)}
    return cubes.filter(**active) if active else cubes


def load_for(config: Config, segment: dict, analysis: str,
             state_dict_version: str) -> CubeSet:
    """세그먼트로 CubeSet 을 로드하고 축으로 좁힌다.

    `dates`·`services` 가 비어 있으면 caller(app.py)가 present 목록으로 채워 넘긴다 —
    여기서는 이미 확정된 값이라고 본다.
    """
    cubes = load_cube_set(
        config,
        dates=segment["dates"],
        services=segment["services"],
        state_dict_version=state_dict_version,
        cube_names=cube_names_for(analysis),
    )
    return apply_segment(cubes, segment)

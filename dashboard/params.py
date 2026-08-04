"""분석별 파라미터 스펙. 순수 데이터 — app.py 가 읽어 위젯을 만든다.

`required=True` 인 파라미터는 값이 없으면 분석을 못 돌린다(app.py 가 막는다). 나머지는
비우면 분석 함수의 기본값을 쓴다(대시보드가 기본을 복제하지 않는다 — 갈라지지 않게).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:
    name: str
    kind: str                    # "int" | "float" | "screen" | "choice" | "pair"
    required: bool = False
    choices: tuple = field(default_factory=tuple)


# 설계 문서 "분석별 파라미터" 표를 그대로 옮긴 것.
ANALYSIS_PARAMS: dict[str, list[Param]] = {
    "reachability": [
        Param("source", "screen", required=True),
        Param("target", "screen", required=True),
        Param("max_k", "int"),
    ],
    "path_ranking": [Param("n", "int", required=True)],
    "click_distribution": [
        Param("by", "choice", choices=("action_kind", "layer1", "layer1,layer2")),
    ],
    "screen_flow": [Param("exit_within", "pair"), Param("damping", "float")],
    "screen_dwell_rank": [Param("warn_below", "float")],
    "screen_communities": [Param("seed", "int"), Param("resolution", "float")],
}


def params_for(analysis: str) -> list[Param]:
    return ANALYSIS_PARAMS.get(analysis, [])


def required_names(analysis: str) -> list[str]:
    return [p.name for p in params_for(analysis) if p.required]

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
    "community_paths": [Param("seed", "int"), Param("resolution", "float"),
                        Param("top_per_community", "int")],
    "hub_neighbors": [Param("screen", "screen")],
}


def params_for(analysis: str) -> list[Param]:
    return ANALYSIS_PARAMS.get(analysis, [])


def required_names(analysis: str) -> list[str]:
    return [p.name for p in params_for(analysis) if p.required]


def coerce(analysis: str, raw_params: dict) -> dict:
    """위젯이 모은 문자열 파라미터를 분석 계약의 타입으로 바꾼다.

    빈 값은 빼서 분석 함수의 기본값을 쓰게 한다(대시보드가 기본을 복제하지 않는다).
    kind 별: int→int, float→float, choice→tuple(콤마 분리), pair→(int, ...), 그 외 문자열.
    """
    specs = {p.name: p for p in params_for(analysis)}
    out: dict = {}
    for name, raw in raw_params.items():
        if raw == "" or raw is None:
            continue
        kind = specs[name].kind if name in specs else "str"
        out[name] = _coerce_one(kind, raw)
    return out


def _coerce_one(kind: str, raw):
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    if kind == "choice":
        return tuple(str(raw).split(","))
    if kind == "pair":
        return tuple(int(x) for x in str(raw).split(","))
    return raw

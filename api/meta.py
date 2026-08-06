"""/api/meta 데이터 조립: 탭·분석 카탈로그·세그먼트 축·present_dates/services.

숫자는 없다 — glossary(한글 라벨)·params(선택지)·filters(축)를 읽어 프론트가 UI 를 짤
메타를 만든다. present_dates 는 디스크에 빌드된 것을 그대로 반영한다(자동 적응).
"""
from __future__ import annotations

from datetime import date

from analytics.analyses.base import list_analyses
from analytics.analyses.cubes import load_cube_set
from dashboard import filters, glossary, params
from data_layer.config import Config

# 정본 빌드(spec 2026-08-06 "정본 빌드 선택"): 6서비스 15일 완성본.
STATE_DICT_VERSION = "sd_2ab5ec25e750dda2"
SERVICES = ["top", "media", "entertain", "sports", "content_v", "search"]

TAB_LABELS = {"overview": "개요", "flow": "화면흐름", "action": "행동",
              "service": "서비스", "quality": "품질"}
TABS = {
    "overview": ["session_trend"],
    "flow": ["screen_flow", "screen_dwell_rank", "screen_pair_affinity",
             "screen_transition", "hub_neighbors", "reachability",
             "screen_communities", "community_paths"],
    "action": ["click_distribution", "conditional_flow", "path_ranking",
               "markov_order_test"],
    "service": ["cross_service_flow"],
    "quality": ["quality_report"],
}

# present_dates 스캔 후보 범위. require_complete=False 라 없는 날짜는 present 교집합에서
# 빠진다 — "지금 디스크에 빌드된 날짜"만 남는다. 넓게 잡아도 session 큐브는 작아 가볍다.
_SCAN_START = "2026-01-01"


def _analysis_catalog() -> list[dict]:
    out = []
    for name in list_analyses():
        specs = params.params_for(name)
        out.append({
            "name": name,
            "label": glossary.analysis_label(name),
            "help": glossary.analysis_desc(name) or None,
            "params": [
                {"name": p.name, "kind": p.kind, "required": p.required,
                 "choices": [str(c) for c in p.choices]}
                for p in specs
            ],
        })
    return out


def _segments() -> list[dict]:
    cubes = load_cube_set(
        Config.from_env(),
        dates=filters.expand_dates(["2026-07-14", "2026-07-28"]),
        services=SERVICES, state_dict_version=STATE_DICT_VERSION,
        cube_names=("session",), require_complete=False,
    )
    s = cubes.session
    return [
        {"axis": a, "label": glossary.axis_label(a),
         "values": [str(v) for v in sorted(s[a].dropna().unique())]}
        for a in filters.SEGMENT_AXES
    ]


def _present_dates() -> list[str]:
    cubes = load_cube_set(
        Config.from_env(),
        dates=filters.expand_dates([_SCAN_START, date.today().isoformat()]),
        services=SERVICES, state_dict_version=STATE_DICT_VERSION,
        cube_names=("session",), require_complete=False,
    )
    return sorted(str(d) for d in cubes.present_dates)


def build_meta() -> dict:
    return {
        "tabs": [{"key": k, "label": v, "analyses": TABS[k]}
                 for k, v in TAB_LABELS.items()],
        "analyses": _analysis_catalog(),
        "segments": _segments(),
        "present_dates": _present_dates(),
        "present_services": list(SERVICES),
        "defaults": {"analysis": "session_trend",
                     "state_dict_version": STATE_DICT_VERSION},
    }

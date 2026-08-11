"""/api/meta 데이터 조립: 탭·분석 카탈로그·세그먼트 축·present_dates/services.

숫자는 없다 — glossary(한글 라벨)·params(선택지)·filters(축)를 읽어 프론트가 UI 를 짤
메타를 만든다. present_dates 는 디스크에 빌드된 것을 그대로 반영한다(자동 적응).
"""
from __future__ import annotations

import functools
from datetime import date

from analytics.analyses.base import CubeSet, list_analyses
from analytics.analyses.cubes import load_cube_set
from dashboard import filters, glossary, params
from data_layer.config import Config

# 정본 빌드(spec 2026-08-06 "정본 빌드 선택"): 7서비스(agorax 포함) 22일 완성본
# (07-14~08-04). state 사전·서비스 목록이 cube_key 를 유도하므로 이 두 상수가 디스크의
# 큐브 디렉토리를 가리킨다 — 오프라인 검증으로 6종 전부 기존 큐브에 적중 확인(재빌드 없음).
STATE_DICT_VERSION = "sd_68461a6e4fc6ccac"
SERVICES = ["top", "media", "entertain", "sports", "content_v", "search", "agorax"]
# 세그먼트 값을 훑을 고정 창(정본 빌드가 실제로 덮는 날짜 범위). 값 목록은 날짜가 늘어도
# 바뀌지 않으므로 넓게 훑을 필요가 없다.
_SEGMENT_SCAN_WINDOW = ("2026-07-14", "2026-07-28")

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


@functools.lru_cache(maxsize=4)
def _load_session(start: str, end: str) -> CubeSet:
    """세션 큐브 실제 로드(공유 캐시). `_segments`·`_present_dates` 가 함께 쓴다.

    build_meta 는 요청마다(Task 4 의 GET /api/meta) 불리므로, 캐시가 없으면 매 요청이
    파케이를 다시 읽는다(약 218일 스캔이면 한 번에 ~0.18초). lru_cache 키는 (start, end)
    문자열 두 개뿐이라 해시 가능하다 — `_present_dates` 는 end 에 `date.today()` 를 넘겨서
    날짜가 바뀌면 키가 바뀌어 하루에 한 번 자연 갱신되고, 같은 날 안에서는 재사용된다.
    `_segments` 는 고정 창이라 프로세스당 한 번만 읽는다.
    """
    return load_cube_set(
        Config.from_env(),
        dates=filters.expand_dates([start, end]),
        services=SERVICES, state_dict_version=STATE_DICT_VERSION,
        cube_names=("session",), require_complete=False,
    )


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
    s = _load_session(*_SEGMENT_SCAN_WINDOW).session
    return [
        {"axis": a, "label": glossary.axis_label(a),
         "values": [str(v) for v in sorted(s[a].dropna().unique())]}
        for a in filters.SEGMENT_AXES
    ]


def _present_dates() -> list[str]:
    cubes = _load_session(_SCAN_START, date.today().isoformat())
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

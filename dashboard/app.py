"""데이터 분석 대시보드 (Streamlit, 단일 모드).

숫자는 analytics/analyses/ 에서만 온다. 이 파일은 위젯으로 상태를 받아 분석을 부르고
render/charts 로 그린다. 상태는 URL query params 에 있어 공유 URL 이 화면을 재현한다.

위젯은 `key` 로 st.session_state 에 상태를 유지한다(클릭이 유지되게). URL 은 최초 로드
때 session_state 를 시드하고, 매 실행 끝에 현재 상태로 갱신된다 — 그래서 클릭으로도
URL 로도 전환되고, 주소를 공유하면 화면이 재현된다.

큐브 로드는 @st.cache_data 로 캐시해 세션끼리 공유한다 — 사내망에서 여러 명이 붙어도
같은 (기간·서비스·분석)은 한 번만 읽는다.

실행: .venv/bin/streamlit run dashboard/app.py  (프로젝트 루트에서)
"""
from __future__ import annotations

import os
import sys

# streamlit run 은 스크립트 디렉토리(dashboard/)만 sys.path 에 넣어 analytics 를 못 찾는다.
# 프로젝트 루트를 직접 얹어 PYTHONPATH 없이도 돌게 한다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from analytics.analyses import get_analysis
from analytics.analyses.cubes import load_cube_set
from dashboard import charts, filters, glossary, params, render
from dashboard.state import decode_state, encode_state
from data_layer.config import Config

STATE_DICT_VERSION = "sd_2ab5ec25e750dda2"

TABS = {
    "overview": ["session_trend"],
    "flow": ["screen_flow", "screen_dwell_rank", "screen_pair_affinity",
             "reachability", "screen_communities"],
    "action": ["click_distribution", "conditional_flow", "path_ranking",
               "markov_order_test"],
    "service": ["cross_service_flow"],
    "quality": ["quality_report"],
}
TAB_LABELS = {"overview": "개요", "flow": "화면흐름", "action": "행동",
              "service": "서비스", "quality": "품질"}
SERVICES = ["top", "media", "entertain", "sports", "content_v", "search"]
DEFAULT_DATES = "2026-07-14:2026-07-28"


@st.cache_data(show_spinner="큐브 로딩…", max_entries=8)
def _load_scope(dates: tuple, services: tuple, analysis: str):
    """(기간·서비스·분석)으로 큐브를 로드한다 — 무거우니 캐시해 세션끼리 공유한다.

    세그먼트 축 필터(apply_segment)는 값이 세션마다 달라 여기서 하지 않는다 —
    캐시 히트율을 높이려고 스코프(빌드 범위)만 캐시하고 축 필터는 호출부에서 건다.
    """
    return load_cube_set(
        Config.from_env(),
        dates=filters.expand_dates(list(dates)),
        services=list(services),
        state_dict_version=STATE_DICT_VERSION,
        cube_names=filters.cube_names_for(analysis),
    )


def safe_tab(tab: str, valid: list[str]) -> str:
    """알 수 없는 tab(손댄 URL)은 기본 탭으로 떨군다 — 크래시 대신."""
    return tab if tab in valid else "overview"


def _seed_from_url() -> None:
    """최초 로드 때 URL → 위젯 session_state 를 시드한다(한 번만).

    이후에는 위젯 key 가 상태의 주인이라, 클릭이 유지되고 매 실행 끝에 URL 로 기록된다.
    분석·파라미터는 탭·분석에 따라 위젯 key 가 달라져 렌더 시점에 시드한다.
    """
    if st.session_state.get("_seeded"):
        return
    s = decode_state(dict(st.query_params))
    keys = list(TAB_LABELS.keys())
    st.session_state["w_tab"] = TAB_LABELS[safe_tab(s["tab"], keys)]
    st.session_state["w_dates"] = ":".join(s["dates"]) or DEFAULT_DATES
    for axis in filters.SEGMENT_AXES:
        st.session_state[f"w_{axis}"] = s.get(axis, "")
    st.session_state["w_top"] = int(s["top"])
    st.session_state["_url_analysis"] = s["analysis"]
    st.session_state["_url_params"] = s["params"]
    st.session_state["_seeded"] = True


def _analysis_widget(tab: str) -> str:
    """탭 안의 분석 selectbox. 탭별 key 라 탭을 바꿔도 각자 선택을 기억한다."""
    tab_analyses = TABS[tab]
    key = f"w_analysis_{tab}"
    if key not in st.session_state:
        url_a = st.session_state.get("_url_analysis")
        st.session_state[key] = url_a if url_a in tab_analyses else tab_analyses[0]
    return st.sidebar.selectbox("분석", tab_analyses, key=key)


def _param_widgets(analysis: str) -> dict:
    """분석별 파라미터 위젯. 분석별 key 라 분석을 바꿔도 각자 값을 기억한다.

    값은 문자열로 모으고(URL 친화), 호출 직전에 params.coerce 로 타입을 맞춘다.
    """
    st.sidebar.markdown("**파라미터**")
    url_params = st.session_state.get("_url_params", {})
    values = {}
    for p in params.params_for(analysis):
        key = f"w_p_{analysis}_{p.name}"
        if p.kind == "choice":
            options = list(p.choices)
            if key not in st.session_state or st.session_state[key] not in options:
                seed = str(url_params.get(p.name, ""))
                st.session_state[key] = seed if seed in options else options[0]
            values[p.name] = st.sidebar.selectbox(p.name, options, key=key)
        else:
            if key not in st.session_state:
                st.session_state[key] = str(url_params.get(p.name, ""))
            raw = st.sidebar.text_input(
                f"{p.name}{' *' if p.required else ''}", key=key)
            if raw:
                values[p.name] = raw
    return values


def _run(state: dict):
    """CubeSet 로드(캐시) → 축 필터 → 분석 호출. 필수 파라미터 없으면 None."""
    missing = [n for n in params.required_names(state["analysis"])
               if n not in state["params"]]
    if missing:
        st.warning(f"필수 파라미터를 입력하세요: {', '.join(missing)}")
        return None
    cubes = _load_scope(tuple(state["dates"]), tuple(state["services"]),
                        state["analysis"])
    cubes = filters.apply_segment(cubes, state)
    call_params = params.coerce(state["analysis"], state["params"])
    return get_analysis(state["analysis"])(cubes, **call_params)


def _draw(result, top: int) -> None:
    """headline 카드 → 표 → 차트 → 봉투."""
    cards = render.headline_cards(result.headline)
    cols = st.columns(len(cards) or 1)
    for col, (key, value) in zip(cols, cards):
        col.metric(glossary.metric_label(key), value,
                   help=glossary.metric_help(key) or None)

    frame = render.table_slice(result.frame, top)
    display = frame.rename(columns={c: glossary.column_label(c)
                                    for c in frame.columns})
    st.dataframe(display, use_container_width=True)

    kind = charts.chart_kind(result.viz)
    x = result.viz.get("x")
    if kind == "bar" and x in result.frame.columns:
        y = next((c for c in result.frame.columns
                  if pd.api.types.is_numeric_dtype(result.frame[c])), None)
        if y:
            st.bar_chart(charts.bar_data(result.frame, x, y, top))
    elif kind == "line" and x in result.frame.columns:
        st.line_chart(charts.line_data(result.frame, x))
    elif kind == "heatmap":
        to = "to_state" if "to_state" in result.frame.columns else "to_service"
        st.dataframe(charts.heatmap_pivot(result.frame, x, to, "cnt"))

    env = render.envelope_summary(result.envelope)
    st.caption(f"⚠ {', '.join(env['warnings']) or '경고 없음'} · "
               f"사전 {env['state_dict_version']} · 날짜 {env['n_dates']}일")


def main():
    st.set_page_config(page_title="데이터 분석 대시보드", layout="wide")
    _seed_from_url()
    keys = list(TAB_LABELS.keys())
    labels = list(TAB_LABELS.values())

    picked = st.radio("모드", labels, key="w_tab", horizontal=True,
                      label_visibility="collapsed")
    tab = keys[labels.index(picked)]

    st.sidebar.header("세그먼트")
    dates = st.sidebar.text_input("기간 (start:end)", key="w_dates")
    # 서비스는 축이 아니라 '빌드 범위'다 — 큐브가 6서비스로 빌드돼 있어 부분 선택은 그
    # 조합 큐브가 없어 에러가 난다. 고정으로 막고, 서비스별 보기는 후속(per_service)으로.
    st.sidebar.multiselect(
        "서비스 (빌드 범위 · 고정)", SERVICES, default=SERVICES, disabled=True,
        help="큐브가 6서비스로 한 번 빌드돼 있어 부분 선택은 안 됩니다. 서비스별로 보려면 "
             "그 서비스로 큐브를 빌드하거나 per_service 분석(후속)을 씁니다.")
    services = list(SERVICES)
    axes = {a: st.sidebar.text_input(a, key=f"w_{a}") for a in filters.SEGMENT_AXES}
    st.sidebar.markdown("---")
    analysis = _analysis_widget(tab)
    param_values = _param_widgets(analysis)
    top = st.number_input("표시 개수", min_value=0, key="w_top")

    state = {
        "mode": "single", "tab": tab, "analysis": analysis,
        "dates": [d for d in dates.split(":") if d],
        "services": list(services),
        **{a: axes[a] for a in filters.SEGMENT_AXES},
        "params": param_values, "top": int(top),
    }

    result = _run(state)
    if result is not None:
        st.subheader(analysis)
        desc = glossary.analysis_desc(analysis)
        if desc:
            st.caption(desc)
        _draw(result, state["top"])
        st.caption(f"표시 {min(state['top'], len(result.frame))} / "
                   f"전체 {len(result.frame)}개")

    # URL 을 매 실행 통째로 덮어쓰면(from_dict) 위젯이 리셋되어 클릭 전환이 막힌다.
    # 자동 갱신을 빼고, 현재 화면을 재현하는 공유 링크를 사이드바에 낸다 — 그 링크로
    # 접속하면 _seed_from_url 이 위젯을 시드해 화면이 재현된다(복사 버튼은 st.code 가 준다).
    share = "&".join(f"{k}={v}" for k, v in encode_state(state).items() if v)
    st.sidebar.markdown("---")
    st.sidebar.caption("이 화면 공유 링크:")
    st.sidebar.code(f"?{share}", language=None)


if __name__ == "__main__":
    main()

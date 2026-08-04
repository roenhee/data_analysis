"""데이터 분석 대시보드 (Streamlit, 단일 모드).

숫자는 analytics/analyses/ 에서만 온다. 이 파일은 위젯으로 상태를 받아 분석을 부르고
render/charts 로 그린다. 상태는 URL query params 에 있어 공유 URL 이 화면을 재현한다.

실행: PYTHONPATH=. .venv/bin/streamlit run dashboard/app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.analyses import get_analysis, list_analyses
from dashboard import charts, filters, params, render
from dashboard.state import DEFAULTS, decode_state, encode_state
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


def _sidebar(state: dict) -> dict:
    """사이드바 위젯 → 갱신된 상태 dict."""
    st.sidebar.header("세그먼트")
    dates = st.sidebar.text_input(
        "기간 (start:end)", ":".join(state["dates"]) or "2026-07-14:2026-07-28")
    state["dates"] = [d for d in dates.split(":") if d]
    state["services"] = st.sidebar.multiselect(
        "서비스 (빌드 범위)", SERVICES, default=state["services"] or ["top"])
    for axis in filters.SEGMENT_AXES:
        state[axis] = st.sidebar.text_input(axis, state.get(axis, ""))

    st.sidebar.markdown("---")
    tab_analyses = TABS[state["tab"]]
    state["analysis"] = st.sidebar.selectbox(
        "분석", tab_analyses,
        index=tab_analyses.index(state["analysis"])
        if state["analysis"] in tab_analyses else 0)

    st.sidebar.markdown("**파라미터**")
    values = {}
    for p in params.params_for(state["analysis"]):
        raw = st.sidebar.text_input(
            f"{p.name}{' *' if p.required else ''}",
            str(state["params"].get(p.name, "")))
        if raw:
            values[p.name] = int(raw) if p.kind == "int" else raw
    state["params"] = values
    return state


def _run(state: dict):
    """CubeSet 로드 → 분석 호출. 필수 파라미터 없으면 None."""
    missing = [n for n in params.required_names(state["analysis"])
               if n not in state["params"]]
    if missing:
        st.warning(f"필수 파라미터를 입력하세요: {', '.join(missing)}")
        return None
    cubes = filters.load_for(Config.from_env(), state, state["analysis"],
                             STATE_DICT_VERSION)
    return get_analysis(state["analysis"])(cubes, **state["params"])


def _draw(result, top: int):
    """headline 카드 → 표 → 차트 → 봉투."""
    cards = render.headline_cards(result.headline)
    cols = st.columns(len(cards) or 1)
    for col, (label, value) in zip(cols, cards):
        col.metric(label, value)

    frame = render.table_slice(result.frame, top)
    st.dataframe(frame, use_container_width=True)

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
    state = decode_state(dict(st.query_params))

    labels = list(TAB_LABELS.values())
    keys = list(TAB_LABELS.keys())
    picked = st.radio("모드", labels, horizontal=True,
                      index=keys.index(state["tab"]), label_visibility="collapsed")
    state["tab"] = keys[labels.index(picked)]

    state = _sidebar(state)
    state["top"] = st.number_input("표시 개수", min_value=0, value=int(state["top"]))

    result = _run(state)
    if result is not None:
        st.subheader(f"{state['analysis']}")
        _draw(result, state["top"])
        st.caption(f"표시 {min(state['top'], len(result.frame))} / "
                   f"전체 {len(result.frame)}개")

    st.query_params.from_dict(encode_state(state))


if __name__ == "__main__":
    main()

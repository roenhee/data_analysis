"""데이터 분석 대시보드 (Streamlit, 단일 모드).

숫자는 analytics/analyses/ 에서만 온다. 이 파일은 위젯으로 상태를 받아 분석을 부르고
render/charts 로 그린다. 상태는 URL query params 로 시드된다(공유 URL 이 화면을 재현).
위계: 헤더(로고+모드) → 컨트롤바(기간·세그먼트) → 탭 → 사이드바(분석 칩+파라미터) → 메인.

실행: .venv/bin/streamlit run dashboard/app.py  (프로젝트 루트에서)
"""
from __future__ import annotations

import os
import sys

# streamlit run 은 스크립트 디렉토리(dashboard/)만 sys.path 에 넣어 analytics 를 못 찾는다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from analytics.analyses import get_analysis
from analytics.analyses.cubes import load_cube_set
from dashboard import charts, filters, glossary, params, render
from dashboard.state import decode_state
from data_layer.config import Config

STATE_DICT_VERSION = "sd_2ab5ec25e750dda2"

TABS = {
    "overview": ["session_trend"],
    "flow": ["screen_flow", "screen_dwell_rank", "screen_pair_affinity",
             "screen_transition", "hub_neighbors", "reachability", "screen_communities",
             "community_paths"],
    "action": ["click_distribution", "conditional_flow", "path_ranking",
               "markov_order_test"],
    "service": ["cross_service_flow"],
    "quality": ["quality_report"],
}
TAB_LABELS = {"overview": "개요", "flow": "화면흐름", "action": "행동",
              "service": "서비스", "quality": "품질"}
SERVICES = ["top", "media", "entertain", "sports", "content_v", "search"]
DEFAULT_DATES = "2026-07-14:2026-07-28"
CHART_TOP = 20     # 차트에 그릴 상위 개수(막대 수천 개 방지). 표는 전량 페이지네이션.
PAGE_SIZE = 50     # 표 한 페이지 행 수.

# 파라미터 이름 → 한글 라벨.
_PARAM_LABELS = {
    "n": "걸음 수 n", "max_k": "최대 걸음", "exit_within": "이탈 구간",
    "damping": "감쇠(damping)", "warn_below": "경고 하한(초)", "seed": "시드",
    "resolution": "해상도", "top_per_community": "군집별 상위 수",
    "source": "출발 화면", "target": "도착 화면", "screen": "화면", "by": "기준",
}
# 파라미터 값 → 드롭다운 표시. 없으면 값 그대로.
_PARAM_VALUE_LABELS = {
    "exit_within": {"": "없음", "1,3": "1~3걸음", "1,5": "1~5걸음", "2,5": "2~5걸음"},
    "by": {"action_kind": "행동 종류", "layer1": "슬롯1", "layer1,layer2": "슬롯1·2"},
}

_HEADER_CSS = """
<style>
#MainMenu, header[data-testid="stHeader"] {visibility: hidden;}
.markov-logo {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 30px; font-weight: 700; letter-spacing: -0.5px;
  color: #4e79a7; line-height: 1.2; margin: 4px 0 0 2px;
  white-space: nowrap;
}
.markov-logo .dot { color: #f28e2b; }
</style>
"""


@st.cache_resource(show_spinner="큐브 로딩…", max_entries=6)
def _load_scope(dates: tuple, services: tuple, cube_names: tuple):
    """(기간·서비스·큐브목록)으로 큐브를 로드한다 — 무거우니 캐시해 세션끼리 공유한다.

    **`@st.cache_resource` 다.** cache_data 는 반환값을 매번 복사·직렬화하는데 path 큐브는
    약 4 GB 라 그 복사가 스트림릿을 멈춰 세운다. cache_resource 는 같은 객체를 그대로 돌려줘
    복사가 없다(큐브는 읽기 전용이라 안전 — 분석은 순수 함수, apply_segment 는 새 프레임).
    """
    return load_cube_set(
        Config.from_env(),
        dates=filters.expand_dates(list(dates)),
        services=list(services),
        state_dict_version=STATE_DICT_VERSION,
        cube_names=tuple(cube_names),
    )


@st.cache_data(show_spinner="세그먼트·날짜 읽는 중…")
def _controls_options() -> tuple[dict, list]:
    """세그먼트 축 값 목록 + 선택 가능한 날짜(present_dates)를 세션 큐브에서(캐시)."""
    cubes = load_cube_set(
        Config.from_env(),
        dates=filters.expand_dates(DEFAULT_DATES.split(":")),
        services=SERVICES, state_dict_version=STATE_DICT_VERSION,
        cube_names=("session",))
    s = cubes.session
    axes = {a: [str(v) for v in sorted(s[a].dropna().unique())]
            for a in filters.SEGMENT_AXES}
    dates = sorted(str(d) for d in cubes.present_dates)
    return axes, dates


@st.cache_data(show_spinner="화면 목록 읽는 중…")
def _screen_options() -> list:
    """화면 이름 목록(transition from/to, START·EXIT 제외). source/target/screen 파라미터용."""
    cubes = load_cube_set(
        Config.from_env(),
        dates=filters.expand_dates(DEFAULT_DATES.split(":")),
        services=SERVICES, state_dict_version=STATE_DICT_VERSION,
        cube_names=("transition",))
    t = cubes.transition
    screens = set(t["from_state"].dropna().unique()) | set(t["to_state"].dropna().unique())
    screens -= {"START", "EXIT"}
    return sorted(screens)


def safe_tab(tab: str, valid: list) -> str:
    """알 수 없는 tab(손댄 URL)은 기본 탭으로 떨군다 — 크래시 대신."""
    return tab if tab in valid else "overview"


def _seed_from_url() -> None:
    """최초 로드 때 URL → 위젯 session_state 를 시드한다(한 번만)."""
    if st.session_state.get("_seeded"):
        return
    s = decode_state(dict(st.query_params))
    keys = list(TAB_LABELS.keys())
    st.session_state["w_tab"] = TAB_LABELS[safe_tab(s["tab"], keys)]
    ds = s["dates"] or DEFAULT_DATES.split(":")
    st.session_state["w_date_start"] = ds[0]
    st.session_state["w_date_end"] = ds[-1]
    for axis in filters.SEGMENT_AXES:
        st.session_state[f"w_{axis}"] = list(s.get(axis, []))
    st.session_state["w_page"] = int(s["page"]) + 1   # state page 는 0-기반, 위젯은 1-기반
    st.session_state["_url_analysis"] = s["analysis"]
    st.session_state["_url_params"] = s["params"]
    st.session_state["_seeded"] = True


def _header() -> None:
    """전체폭 헤더: Markov 로고 + 단일/비교 모드 탭(비교는 다음 단계라 비활성)."""
    st.markdown(_HEADER_CSS, unsafe_allow_html=True)
    left, right = st.columns([2, 6])
    left.markdown('<div class="markov-logo">Markov<span class="dot">.</span></div>',
                  unsafe_allow_html=True)
    with right:
        st.segmented_control(
            "모드", ["단일", "비교"], default="단일", key="w_mode",
            disabled=True, label_visibility="collapsed",
            help="비교 모드는 다음 단계에서 열립니다")


def _analysis_widget(tab: str) -> str:
    """탭 안 분석을 칩(pills)으로. 한글 라벨 표시, 값은 분석 이름. 탭별 key 로 선택 기억."""
    tab_analyses = TABS[tab]
    key = f"w_analysis_{tab}"
    if key not in st.session_state:
        url_a = st.session_state.get("_url_analysis")
        st.session_state[key] = url_a if url_a in tab_analyses else tab_analyses[0]
    picked = st.sidebar.pills(
        "분석", tab_analyses, format_func=glossary.analysis_label,
        selection_mode="single", key=key)
    return picked or tab_analyses[0]


def _param_widgets(analysis: str) -> dict:
    """분석별 파라미터를 드롭다운으로. 값은 문자열로 모으고 호출 직전 coerce 로 타입을 맞춘다."""
    specs = params.params_for(analysis)
    if not specs:
        return {}
    st.sidebar.markdown("**파라미터**")
    url_params = st.session_state.get("_url_params", {})
    values = {}
    for p in specs:
        key = f"w_p_{analysis}_{p.name}"
        label = _PARAM_LABELS.get(p.name, p.name) + (" *" if p.required else "")
        if p.kind == "screen":
            opts = _screen_options()
            if not p.required:
                opts = [""] + opts
            if key not in st.session_state or st.session_state[key] not in opts:
                seed = str(url_params.get(p.name, ""))
                st.session_state[key] = seed if seed in opts else opts[0]
            val = st.sidebar.selectbox(
                label, opts, key=key,
                format_func=lambda v: glossary.value_label(v) if v else "(자동)")
        else:
            opts = [str(c) for c in p.choices]
            if key not in st.session_state or st.session_state[key] not in opts:
                seed = str(url_params.get(p.name, ""))
                st.session_state[key] = seed if seed in opts else opts[0]
            vlabels = _PARAM_VALUE_LABELS.get(p.name, {})
            val = st.sidebar.selectbox(
                label, opts, key=key,
                format_func=lambda v, m=vlabels: m.get(v, v if v != "" else "없음"))
        if val != "":
            values[p.name] = val
    return values


def _run(state: dict):
    """CubeSet 로드(캐시) → 축 필터 → 분석 호출. 필수 파라미터 없으면 None."""
    missing = [n for n in params.required_names(state["analysis"])
               if n not in state["params"]]
    if missing:
        st.warning(f"필수 파라미터를 선택하세요: {', '.join(missing)}")
        return None
    cubes = _load_scope(tuple(state["dates"]), tuple(state["services"]),
                        tuple(sorted(filters.cube_names_for(state["analysis"]))))
    cubes = filters.apply_segment(cubes, state)
    call_params = params.coerce(state["analysis"], state["params"])
    return get_analysis(state["analysis"])(cubes, **call_params)


def _draw(result) -> None:
    """headline 카드 → 표(페이지네이션) → 차트 → 봉투."""
    cards = render.headline_cards(result.headline)
    cols = st.columns(len(cards) or 1)
    for col, (key, value) in zip(cols, cards):
        col.metric(glossary.metric_label(key), value,
                   help=glossary.metric_help(key) or None)

    display = result.frame.copy()
    for c in display.columns:
        if display[c].dtype == object:
            display[c] = display[c].map(
                lambda v: glossary.value_label(v) if isinstance(v, str) else v)
    page = int(st.session_state.get("w_page", 1)) - 1   # 위젯은 1-기반, 슬라이스는 0-기반
    sliced, n_pages = render.page_slice(display, page, PAGE_SIZE)
    st.dataframe(
        sliced, use_container_width=True,
        column_config={c: st.column_config.Column(
            glossary.column_label(c), help=glossary.column_help(c) or None)
            for c in display.columns})
    if n_pages > 1:
        st.number_input(f"페이지 (전체 {n_pages}쪽 · {len(display):,}행)",
                        min_value=1, max_value=n_pages, step=1, key="w_page")

    if result.viz.get("kind") == "graph":
        st.graphviz_chart(
            charts.graph_dot(result.frame, result.viz, label_of=glossary.value_label),
            use_container_width=True)
    else:
        kind = charts.chart_kind(result.viz)
        x = result.viz.get("x")
        if kind == "bar" and x in result.frame.columns:
            y = next((c for c in result.frame.columns
                      if pd.api.types.is_numeric_dtype(result.frame[c])), None)
            if y:
                st.altair_chart(charts.bar_chart(result.frame, x, y, CHART_TOP),
                                use_container_width=True)
        elif kind == "line" and x in result.frame.columns:
            st.altair_chart(charts.line_chart(result.frame, x),
                            use_container_width=True)
        elif kind == "heatmap":
            to = "to_state" if "to_state" in result.frame.columns else "to_service"
            value = result.viz.get("value", "cnt")
            st.altair_chart(charts.heatmap_chart(result.frame, x, to, value),
                            use_container_width=True)

    env = render.envelope_summary(result.envelope)
    warns = [glossary.warning_label(w) for w in env["warnings"]]
    st.caption(f"⚠ {', '.join(warns) or '경고 없음'} · "
               f"사전 {env['state_dict_version']} · 날짜 {env['n_dates']}일")


def main():
    st.set_page_config(page_title="Markov 대시보드", layout="wide")
    _seed_from_url()
    _header()

    # ── 상단 컨트롤바: 기간(드롭다운) + 세그먼트 축 (서비스는 고정 전체라 위젯 없음) ──
    axes_opts, date_opts = _controls_options()
    with st.container(border=True):
        r1 = st.columns([2, 2, 4])
        start = r1[0].selectbox("시작일", date_opts, key="w_date_start")
        end = r1[1].selectbox("종료일", date_opts, key="w_date_end")
        axes = {}
        acols = st.columns(len(filters.SEGMENT_AXES))
        for i, a in enumerate(filters.SEGMENT_AXES):
            choices = axes_opts.get(a, [])
            st.session_state[f"w_{a}"] = [
                v for v in st.session_state.get(f"w_{a}", []) if v in choices]
            axes[a] = acols[i].multiselect(
                glossary.axis_label(a), choices, key=f"w_{a}",
                format_func=lambda v, ax=a: glossary.axis_value_label(ax, v),
                help=glossary.axis_help(a))

    # ── 분석 탭 ──
    keys = list(TAB_LABELS.keys())
    labels = list(TAB_LABELS.values())
    picked = st.radio("탭", labels, key="w_tab", horizontal=True,
                      label_visibility="collapsed")
    tab = keys[labels.index(picked)]

    # ── 사이드바: 분석 칩 + 파라미터 ──
    analysis = _analysis_widget(tab)
    param_values = _param_widgets(analysis)

    state = {
        "mode": "single", "tab": tab, "analysis": analysis,
        "dates": [start, end],
        "services": list(SERVICES),
        **{a: axes[a] for a in filters.SEGMENT_AXES},
        "params": param_values, "page": int(st.session_state.get("w_page", 1)) - 1,
    }

    result = _run(state)
    if result is not None:
        st.subheader(glossary.analysis_label(analysis))
        desc = glossary.analysis_desc(analysis)
        if desc:
            st.caption(desc)
        _draw(result)


if __name__ == "__main__":
    main()

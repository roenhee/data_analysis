# 대시보드 UX 개편 1단계 (공통 골격) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단일 모드 대시보드를 **B형 레이아웃(상단 컨트롤바)** + **Vega-Lite(Altair) 차트** + **페이지네이션**으로 재구성하고, 16개 분석이 회귀 없이 렌더되게 한다.

**Architecture:** `dashboard/` 의 순수 함수(`charts`·`render`·`state`)는 TDD 로 바꾸고, Streamlit 위젯을 엮는 `app.py` 는 얇게 유지해 수동 스모크로 확인한다. 시각화는 **Altair 차트 객체를 반환하는 순수 함수**로 만들고 `app.py` 가 `st.altair_chart` 로 그린다. `graph` 는 예외 — 기존 `graph_dot()` + `st.graphviz_chart` 를 그대로 둔다. 숫자는 여전히 `analytics/analyses/` 만 만든다.

**Tech Stack:** Streamlit 1.60, Altair 6.2.2, pandas. 설계: `docs/superpowers/specs/2026-08-05-dashboard-ux-revamp-design.md`.

---

## File Structure

| 파일 | 이 계획에서의 변경 |
|---|---|
| `dashboard/charts.py` | `bar_data`/`line_data`/`heatmap_pivot`(데이터 준비) → `bar_chart`/`line_chart`/`heatmap_chart`(**Altair 차트 반환**). `chart_kind`·`graph_dot` 은 그대로. |
| `dashboard/render.py` | `table_slice`(top 자르기) → `page_slice`(**페이지네이션**). `headline_cards`·`envelope_summary` 그대로. |
| `dashboard/state.py` | `DEFAULTS` 에서 `top` 제거, `page` 추가. `_INT_KEYS` 교체. |
| `dashboard/app.py` | **B형 레이아웃**: 세그먼트를 상단 컨트롤바로, 사이드바는 분석·파라미터만. 표시개수 위젯 제거, **페이지 위젯** 추가. `st.bar_chart`/`st.line_chart`/heatmap `st.dataframe` → `st.altair_chart`. `[단일\|비교]` 자리(단일 고정). |
| `tests/dashboard/test_charts.py` | `bar_data`/`line_data`/`heatmap_pivot` 테스트 → `bar_chart`/`line_chart`/`heatmap_chart`(Altair 스펙 검증). `graph_dot` 테스트 유지. |
| `tests/dashboard/test_render.py` | `table_slice` 테스트 → `page_slice`. 나머지 유지. |
| `tests/dashboard/test_state.py` | `top` 테스트 → `page`. |

`app.py` 만 자동 테스트가 없고(수동 스모크), 나머지는 순수 함수라 TDD.

**차트 상위 개수 상수**: `app.py` 에 `CHART_TOP = 20` 을 둔다(막대 수천 개 방지). 표는 전량 페이지네이션.
**페이지 크기 상수**: `app.py` 에 `PAGE_SIZE = 50`.

---

## Task 1: `charts.py` — Vega-Lite bar/line/heatmap

`viz.kind`(bar/line/heatmap)를 **Altair 차트 객체**로 만든다. `app.py` 가 `st.altair_chart` 로 그린다. `chart_kind`(분류)와 `graph_dot`(graphviz)은 손대지 않는다.

**Files:**
- Modify: `dashboard/charts.py`
- Test: `tests/dashboard/test_charts.py`

- [ ] **Step 1: 실패 테스트로 교체**

`tests/dashboard/test_charts.py` 의 `bar_data`·`line_data`·`heatmap_pivot` 세 테스트(19~53행)를 아래로 **교체**한다. import 줄과 `graph_dot` 테스트(56행 이하)는 그대로 둔다.

import 줄을 바꾼다:
```python
import pandas as pd

from dashboard.charts import chart_kind, bar_chart, line_chart, heatmap_chart, graph_dot
```

`chart_kind` 테스트 3개(`test_chart_kind_reads_viz`·`test_graph_falls_back_to_table_in_this_plan`·`test_missing_kind_is_table`)는 그대로 두고, 그 아래 `bar_data`~`heatmap_pivot` 테스트만 아래로 교체:
```python
def test_bar_chart_is_a_bar_encoding_x_and_y():
    frame = pd.DataFrame({"state": ["a", "b", "c"], "pagerank": [0.3, 0.5, 0.2]})
    spec = bar_chart(frame, x="state", y="pagerank", top=3).to_dict()
    assert spec["mark"]["type"] == "bar"
    assert spec["encoding"]["x"]["field"] == "state"
    assert spec["encoding"]["y"]["field"] == "pagerank"


def test_bar_chart_limits_to_top():
    frame = pd.DataFrame({"state": list("abcde"), "v": [5, 4, 3, 2, 1]})
    ch = bar_chart(frame, x="state", y="v", top=2)
    assert len(ch.data) == 2


def test_bar_chart_sorts_by_value_descending():
    frame = pd.DataFrame({"state": ["a", "b"], "v": [1.0, 2.0]})
    spec = bar_chart(frame, x="state", y="v", top=2).to_dict()
    assert spec["encoding"]["x"]["sort"] == "-y"


def test_line_chart_folds_numeric_columns_into_series():
    """session_trend 처럼 수치 열이 여럿이면 색으로 구분한 여러 선이 된다."""
    frame = pd.DataFrame({"period": ["d1", "d2"], "sessions": [10, 20], "pv": [30, 40]})
    spec = line_chart(frame, x="period").to_dict()
    assert spec["mark"]["type"] == "line"
    assert spec["encoding"]["color"]["field"] == "series"


def test_line_chart_drops_non_numeric_columns():
    """문자열 열(요일 등)은 선으로 그리지 않는다."""
    frame = pd.DataFrame({"period": ["d1", "d2"], "sessions": [10, 20], "weekday": ["월", "화"]})
    ch = line_chart(frame, x="period")
    assert set(ch.data["series"].unique()) == {"sessions"}


def test_heatmap_chart_is_a_rect_mark_with_color_value():
    frame = pd.DataFrame({
        "from_state": ["a", "a", "b"], "to_state": ["a", "b", "a"], "cnt": [1, 2, 3],
    })
    spec = heatmap_chart(frame, x="from_state", to="to_state", value="cnt").to_dict()
    assert spec["mark"]["type"] == "rect"
    assert spec["encoding"]["x"]["field"] == "from_state"
    assert spec["encoding"]["y"]["field"] == "to_state"
    assert spec["encoding"]["color"]["field"] == "cnt"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_charts.py -q`
Expected: FAIL — `ImportError: cannot import name 'bar_chart'`

- [ ] **Step 3: charts.py 구현**

`dashboard/charts.py` 의 상단 docstring·`_SUPPORTED`·`chart_kind` 는 유지하고, `bar_data`·`line_data`·`heatmap_pivot`(25~39행)을 아래로 **교체**한다. `graph_dot`·`_PALETTE` 는 그대로 둔다. 파일 맨 위 import 에 `import altair as alt` 를 추가한다.

```python
import altair as alt
import pandas as pd

_SUPPORTED = {"bar", "line", "heatmap"}
_BAR_COLOR = "#4e79a7"

# (_PALETTE 는 기존 그대로 아래에 유지)


def chart_kind(viz: dict) -> str:
    """그릴 차트 종류. 지원 안 하는 kind(graph 는 app.py 가 따로 그린다)는 표로."""
    kind = viz.get("kind", "table")
    return kind if kind in _SUPPORTED else "table"


def bar_chart(frame: pd.DataFrame, x: str, y: str, top: int) -> alt.Chart:
    """상위 top 행을 y 내림차순 막대로. 단색·툴팁·정렬 제어(Streamlit 기본과 달리)."""
    data = frame.head(max(0, top))
    return (
        alt.Chart(data)
        .mark_bar(color=_BAR_COLOR)
        .encode(
            x=alt.X(f"{x}:N", sort="-y", title=None),
            y=alt.Y(f"{y}:Q", title=None),
            tooltip=[x, y],
        )
    )


def line_chart(frame: pd.DataFrame, x: str) -> alt.Chart:
    """x 를 축으로, 수치 열들을 색으로 구분한 여러 선. 문자열 열은 뺀다."""
    num = [c for c in frame.select_dtypes(include="number").columns if c != x]
    long = frame.melt(id_vars=[x], value_vars=num,
                      var_name="series", value_name="value")
    return (
        alt.Chart(long)
        .mark_line(point=True)
        .encode(
            x=alt.X(x, title=None),
            y=alt.Y("value:Q", title=None),
            color=alt.Color("series:N", scale=alt.Scale(range=_PALETTE), title=None),
            tooltip=[x, "series", "value"],
        )
    )


def heatmap_chart(frame: pd.DataFrame, x: str, to: str, value: str) -> alt.Chart:
    """(x, to) 격자를 색 농도로. 진짜 히트맵 — 표+그라데이션이 아니다."""
    return (
        alt.Chart(frame)
        .mark_rect()
        .encode(
            x=alt.X(f"{x}:N", title=None),
            y=alt.Y(f"{to}:N", title=None),
            color=alt.Color(f"{value}:Q", scale=alt.Scale(scheme="blues"), title=None),
            tooltip=[x, to, value],
        )
    )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_charts.py -q`
Expected: PASS (chart_kind 3 + bar 3 + line 2 + heatmap 1 + graph_dot 6)

- [ ] **Step 5: 커밋**

```bash
git add dashboard/charts.py tests/dashboard/test_charts.py
git commit -m "feat(dashboard): Vega-Lite (Altair) bar/line/heatmap charts"
```

---

## Task 2: `render.py` — 페이지네이션

`table_slice`(상위 top 자르기)를 `page_slice`(페이지 단위 슬라이스 + 총 페이지 수)로 바꾼다. `headline_cards`·`envelope_summary` 는 그대로.

**Files:**
- Modify: `dashboard/render.py`
- Test: `tests/dashboard/test_render.py`

- [ ] **Step 1: 실패 테스트로 교체**

`tests/dashboard/test_render.py` 의 import 줄과 `table_slice` 테스트 2개(26~34행)를 교체한다. `headline_cards`·`envelope_summary` 테스트는 유지.

import 줄:
```python
from dashboard.render import headline_cards, page_slice, envelope_summary
```

`test_table_slice_takes_top_n`·`test_table_slice_zero_or_negative_is_empty` 를 아래로 교체:
```python
def test_page_slice_returns_the_page_rows_and_page_count():
    frame = pd.DataFrame({"x": range(120)})
    rows, n_pages = page_slice(frame, page=0, page_size=50)
    assert list(rows["x"]) == list(range(50))
    assert n_pages == 3          # ceil(120/50)


def test_page_slice_second_page():
    frame = pd.DataFrame({"x": range(120)})
    rows, _ = page_slice(frame, page=1, page_size=50)
    assert list(rows["x"]) == list(range(50, 100))


def test_page_slice_last_page_is_partial():
    frame = pd.DataFrame({"x": range(120)})
    rows, _ = page_slice(frame, page=2, page_size=50)
    assert list(rows["x"]) == list(range(100, 120))


def test_page_slice_clamps_out_of_range_page():
    """손댄 URL 로 페이지가 범위를 넘으면 마지막 페이지로 떨군다 — 크래시 대신."""
    frame = pd.DataFrame({"x": range(10)})
    rows, n_pages = page_slice(frame, page=99, page_size=50)
    assert n_pages == 1
    assert list(rows["x"]) == list(range(10))


def test_page_slice_empty_frame_is_one_page():
    frame = pd.DataFrame({"x": []})
    rows, n_pages = page_slice(frame, page=0, page_size=50)
    assert len(rows) == 0
    assert n_pages == 1
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_render.py -q`
Expected: FAIL — `ImportError: cannot import name 'page_slice'`

- [ ] **Step 3: 구현**

`dashboard/render.py` 의 `table_slice`(28~30행)를 아래로 교체한다. `import math` 는 이미 있다.
```python
def page_slice(frame: pd.DataFrame, page: int, page_size: int):
    """(그 페이지의 행, 총 페이지 수). 범위 밖 page 는 마지막으로 떨군다.

    표시 개수 입력을 없앤 대신 전체를 페이지로 넘겨본다 — 상위 N 만 보이던 걸 다 볼 수 있다.
    """
    n = len(frame)
    n_pages = max(1, math.ceil(n / page_size))
    page = max(0, min(page, n_pages - 1))
    start = page * page_size
    return frame.iloc[start:start + page_size], n_pages
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_render.py -q`
Expected: PASS (headline 3 + page_slice 5 + envelope 1)

- [ ] **Step 5: 커밋**

```bash
git add dashboard/render.py tests/dashboard/test_render.py
git commit -m "feat(dashboard): pagination slice replaces top-N table slice"
```

---

## Task 3: `state.py` — `top` 제거, `page` 추가

표시 개수(`top`)를 없애고 페이지(`page`)를 URL 상태로 왕복시킨다.

**Files:**
- Modify: `dashboard/state.py`
- Test: `tests/dashboard/test_state.py`

- [ ] **Step 1: 실패 테스트로 교체**

`tests/dashboard/test_state.py` 의 `test_scalar_round_trip`(9~11행)에서 `top` 을 `page` 로 바꾼다:
```python
def test_scalar_round_trip():
    state = {**DEFAULTS, "analysis": "screen_flow", "page": 2}
    assert decode_state(encode_state(state)) == state
```
나머지 테스트는 그대로 둔다.

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_state.py -q`
Expected: FAIL — `KeyError: 'page'` (또는 `top` 이 DEFAULTS 에 남아 왕복 불일치)

- [ ] **Step 3: 구현**

`dashboard/state.py` 의 `DEFAULTS` 에서 `"top": 10,` 을 `"page": 0,` 으로 바꾸고, `_INT_KEYS = ("top",)` 을 `_INT_KEYS = ("page",)` 로 바꾼다. 나머지는 그대로.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_state.py -q`
Expected: PASS (7개)

- [ ] **Step 5: 커밋**

```bash
git add dashboard/state.py tests/dashboard/test_state.py
git commit -m "feat(dashboard): url state carries page instead of top-N"
```

---

## Task 4: `app.py` — B형 레이아웃 재구성 (수동 스모크)

세그먼트를 상단 컨트롤바로 올리고, 사이드바는 분석·파라미터만 남긴다. 표시개수 위젯을 없애고 페이지 위젯을 넣는다. 차트를 `st.altair_chart` 로 그린다. **이 파일은 자동 테스트가 없다 — 얇게 유지하고 브라우저 스모크로 확인한다.**

**Files:**
- Modify: `dashboard/app.py`
- Test(유지): `tests/dashboard/test_app.py` (`safe_tab` 만, 변경 없음)

- [ ] **Step 1: 상수·`_draw` 교체**

`app.py` 상단 상수 블록(`STATE_DICT_VERSION`~`DEFAULT_DATES`) 바로 아래에 추가:
```python
CHART_TOP = 20     # 차트에 그릴 상위 개수(막대 수천 개 방지). 표는 전량 페이지네이션.
PAGE_SIZE = 50     # 표 한 페이지 행 수.
```

`_draw(result, top)` 함수 전체(165~210행)를 아래 `_draw(result)` 로 **교체**한다(더 이상 `top` 인자를 받지 않는다):
```python
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
```

- [ ] **Step 2: `main()` 재구성 — 세그먼트를 상단 컨트롤바로**

`main()` 전체(213~273행)를 아래로 **교체**한다. 핵심 변경: (1) `[단일|비교]` + 세그먼트를 `st.columns` 로 상단에, (2) 사이드바엔 분석·파라미터만, (3) 표시개수 `number_input` 삭제(페이지는 `_draw` 안에서).
```python
def main():
    st.set_page_config(page_title="데이터 분석 대시보드", layout="wide")
    _seed_from_url()
    keys = list(TAB_LABELS.keys())
    labels = list(TAB_LABELS.values())

    # ── 상단 컨트롤바: [단일|비교] + 세그먼트 ──
    top = st.container()
    with top:
        head = st.columns([1.2, 2, 1.4, 1, 1, 1, 1, 1])
        # [단일|비교] — 비교는 3단계에서 활성. 지금은 단일 고정(비활성 표시).
        head[0].radio("모드", ["단일", "비교"], key="w_mode",
                      horizontal=True, label_visibility="collapsed",
                      disabled=True,
                      help="비교 모드는 준비 중입니다(다음 단계).")
        dates = head[1].text_input("기간 (start:end)", key="w_dates")
        head[2].multiselect(
            "서비스 (빌드 범위·고정)", SERVICES, default=SERVICES, disabled=True,
            help="큐브가 6서비스로 빌드돼 있어 부분 선택은 안 됩니다.")
        services = list(SERVICES)
        opts = _axis_options()
        axes = {}
        for i, a in enumerate(filters.SEGMENT_AXES):
            choices = opts.get(a, [])
            st.session_state[f"w_{a}"] = [
                v for v in st.session_state.get(f"w_{a}", []) if v in choices]
            axes[a] = head[3 + i].multiselect(
                glossary.axis_label(a), choices, key=f"w_{a}",
                format_func=lambda v, ax=a: glossary.axis_value_label(ax, v),
                help=glossary.axis_help(a) + " (여러 개, 비우면 전체)")

    # ── 분석 탭 ──
    picked = st.radio("탭", labels, key="w_tab", horizontal=True,
                      label_visibility="collapsed")
    tab = keys[labels.index(picked)]

    # ── 사이드바: 분석 + 파라미터 ──
    analysis = _analysis_widget(tab)
    param_values = _param_widgets(analysis)

    state = {
        "mode": "single", "tab": tab, "analysis": analysis,
        "dates": [d for d in dates.split(":") if d],
        "services": list(services),
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

    share = "&".join(f"{k}={v}" for k, v in encode_state(state).items() if v)
    st.sidebar.markdown("---")
    st.sidebar.caption("이 화면 공유 링크:")
    st.sidebar.code(f"?{share}", language=None)
```

`_analysis_widget`·`_param_widgets` 는 `st.sidebar.*` 를 쓰므로 사이드바에 그대로 남는다 — 변경 없다. `_seed_from_url` 의 `st.session_state["w_top"]` 줄(107행)은 삭제한다(`top` 상태가 사라졌다).

- [ ] **Step 3: `_seed_from_url` 정리**

`_seed_from_url` 에서 `st.session_state["w_top"] = int(s["top"])` 줄을 삭제한다. `page` 는 위젯 기본(1)에서 시작하므로 시드하지 않아도 된다.

- [ ] **Step 4: import 스모크**

Run: `.venv/bin/python -c "import dashboard.app"`
Expected: 출력 없음, exit 0 (임포트 에러 없음)

- [ ] **Step 5: 대시보드 유닛 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard -q`
Expected: PASS (charts·render·state·filters·params·glossary·app 전부)

- [ ] **Step 6: 브라우저 수동 스모크**

`.claude/launch.json` 의 `dashboard` 설정으로 preview 를 띄우고 확인한다(크레덴셜은 `env.py` → `os.environ` 주입 필요 — 실행 셸에 `TIARA_ID`/`TIARA_PW` 가 있어야 큐브 로드가 된다):
- 상단에 `[단일|비교]`(비교 비활성) + 기간·서비스·축 6개가 **한 줄 컨트롤바**로 뜬다.
- 사이드바엔 **분석·파라미터·공유링크만** 남는다.
- 화면흐름 › screen_flow: 지표카드 → 표 → **Altair 막대차트**(정렬·색·툴팁) → 봉투.
- 서비스 탭 › cross_service_flow: **Altair 히트맵**(표+색 아님, 진짜 rect 격자).
- 개요 › session_trend: **Altair 라인**(여러 수치 열이 색으로 구분).
- 표가 50행을 넘으면 **페이지 위젯**이 뜨고, 페이지를 바꾸면 표가 바뀐다.
- 표시개수 입력 위젯이 **없다**.
- 화면 군집 › screen_communities: graphviz 네트워크가 **그대로** 나온다.
- 주소창 URL 복사 → 새 탭에 붙이면 같은 화면 재현(page 포함).

**밀도 조정(스모크에서):** 상단 컨트롤바가 축 6개로 좁으면 `st.columns` 비율을 조정하거나 축 일부를 `st.popover`("세그먼트 더보기")로 접는다. 설계 문서 "열린 질문" 참고.

- [ ] **Step 7: 커밋**

```bash
git add dashboard/app.py
git commit -m "feat(dashboard): B-layout top control-bar, altair charts, pagination"
```

---

## Task 5: 전체 스위트 + 문서

**Files:**
- Modify: `dashboard/README.md`

- [ ] **Step 1: README 갱신**

`dashboard/README.md` 에 레이아웃/시각화 변경을 반영한다(단일 모드·URL 공유 설명은 유지, "Streamlit 기본 차트" 언급이 있으면 "Vega-Lite(Altair)" 로, 표시개수 언급이 있으면 페이지네이션으로).

- [ ] **Step 2: 전체 테스트가 안 깨졌는지 확인**

Run: `find . -path ./.venv -prune -o -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; .venv/bin/python -m pytest tests -q -p no:cacheprovider`
Expected: 기존 그린 + 대시보드 변경분 전부 통과(회귀 없음).

- [ ] **Step 3: 커밋**

```bash
git add dashboard/README.md
git commit -m "docs(dashboard): note B-layout, Vega-Lite, pagination"
```

---

## Self-Review

**1. Spec coverage (설계 문서 대비):**
- B형 레이아웃(상단 컨트롤바·얇은 사이드바) → Task 4 `main`.
- `[단일\|비교]` 자리(단일 고정) → Task 4 `main` (disabled radio).
- Vega-Lite 전환(bar/line/heatmap) → Task 1 `charts.py`.
- heatmap 진짜 히트맵 → Task 1 `heatmap_chart` (mark_rect).
- graph 는 graphviz 유지 → Task 4 `_draw` (graph 분기 그대로).
- 표시개수 위젯 제거 + 페이지네이션 → Task 2 `page_slice` + Task 3 `state.page` + Task 4 `_draw`/`main`.
- 차트 상위 N 고정 → Task 4 `CHART_TOP`.
- 16개 분석 회귀 없이 렌더 → Task 4 Step 5·6 (유닛 + 스모크).

**2. Placeholder scan:** 각 코드 step 에 완전한 코드/교체 지점이 있음. "TODO"/"적절히" 없음. 밀도 조정은 스모크 안내(코드 있음)로 명시.

**3. Type consistency:** `bar_chart(frame,x,y,top)`·`line_chart(frame,x)`·`heatmap_chart(frame,x,to,value)` → Task 4 `_draw` 호출과 시그니처 일치. `page_slice(frame,page,page_size) -> (rows, n_pages)` → Task 4 `_draw` 사용과 일치. `state["page"]` (0-기반) ↔ 위젯 `w_page`(1-기반) 변환을 `_draw`·`main` 양쪽에서 `-1` 로 맞춤.

**주의(구현자에게):**
- Altair `to_dict()` 의 `mark` 는 dict(`{"type": "bar", ...}`)다 — 테스트가 `spec["mark"]["type"]` 로 읽는다.
- `line_chart` 는 `melt` 로 long-form 을 만든다. `x` 열이 수치가 아니어야 정상(period·k). 만약 수치 x(reachability 의 `k`)면 그 열도 `select_dtypes` 에 잡히므로 `if c != x` 로 뺀다(이미 반영).
- 스모크는 **크레덴셜이 있는 셸**에서만 큐브가 로드된다. 유닛 테스트(Task 1~3)는 크레덴셜 불필요.

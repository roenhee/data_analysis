# Dashboard Skeleton + Single Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세그먼트·파라미터를 골라 12개 분석을 단일 모드로 보고, URL 을 복사해 다시 열면 같은 화면이 재현되는 Streamlit 대시보드 골격.

**Architecture:** `dashboard/` 새 패키지. 숫자는 전부 `analytics/analyses/` 를 호출하고 대시보드는 UI 만 담당한다. 계산 없는 순수 함수(URL 상태, 파라미터 스펙, 결과 변환, 차트 데이터 준비)는 TDD 로 테스트하고, Streamlit 위젯을 엮는 `app.py` 는 얇게 유지해 수동 스모크로 확인한다.

**Tech Stack:** Streamlit, pandas. 설계: `docs/superpowers/specs/2026-08-04-dashboard-design.md`.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `dashboard/state.py` | 상태 dict ↔ URL query params (순수). 왕복 항등이 1급 테스트. |
| `dashboard/params.py` | 분석별 파라미터 스펙(어떤 입력이 필요한가). 순수 데이터. |
| `dashboard/render.py` | `AnalysisResult` → headline 카드·표 slice·봉투 요약 (순수 변환). |
| `dashboard/charts.py` | `viz.kind` → 차트 데이터 준비 (순수). `st.*` 호출 없음. |
| `dashboard/filters.py` | 세그먼트 dict → `load_cube_set` + `cubes.filter` (CubeSet 로딩). |
| `dashboard/app.py` | Streamlit 진입. 위계(탭)·위젯·URL 배선. `st.*` 는 여기만. |

테스트는 `tests/dashboard/` 아래 파일별로. `app.py` 만 자동 테스트가 없고 수동 스모크.

---

### Task 0: 패키지 뼈대 + 의존

**Files:**
- Create: `dashboard/__init__.py`
- Create: `tests/dashboard/__init__.py`

- [ ] **Step 1: streamlit 설치**

Run: `.venv/bin/pip install streamlit`
Expected: `Successfully installed streamlit-...`

- [ ] **Step 2: 설치 확인**

Run: `.venv/bin/python -c "import streamlit; print(streamlit.__version__)"`
Expected: 버전 문자열(예: `1.3x.x`)

- [ ] **Step 3: 빈 패키지 파일 생성**

`dashboard/__init__.py`:
```python
"""데이터 분석 대시보드 (Streamlit). 숫자는 analytics/analyses/ 에서만 온다."""
```

`tests/dashboard/__init__.py`:
```python
```

- [ ] **Step 4: 커밋**

```bash
git add dashboard/__init__.py tests/dashboard/__init__.py
git commit -m "feat(dashboard): package skeleton and streamlit dependency"
```

---

### Task 1: `state.py` — URL 상태 왕복

상태를 URL query params 로 인코딩/디코딩한다. `decode(encode(s))` 가 항등이어야 공유 URL 이 화면을 정확히 재현한다.

**Files:**
- Create: `dashboard/state.py`
- Test: `tests/dashboard/test_state.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/dashboard/test_state.py`:
```python
from dashboard.state import encode_state, decode_state, DEFAULTS


def test_defaults_round_trip():
    """빈 params 는 기본 상태로 디코딩된다."""
    assert decode_state({}) == DEFAULTS


def test_scalar_round_trip():
    state = {**DEFAULTS, "analysis": "screen_flow", "service_type": "MA", "top": 25}
    assert decode_state(encode_state(state)) == state


def test_services_list_round_trips_as_csv():
    """서비스는 다중이라 콤마로 인코딩된다."""
    state = {**DEFAULTS, "services": ["top", "media"]}
    encoded = encode_state(state)
    assert encoded["services"] == "top,media"
    assert decode_state(encoded)["services"] == ["top", "media"]


def test_date_range_round_trips_as_colon():
    state = {**DEFAULTS, "dates": ["2026-07-14", "2026-07-28"]}
    encoded = encode_state(state)
    assert encoded["dates"] == "2026-07-14:2026-07-28"
    assert decode_state(encoded)["dates"] == ["2026-07-14", "2026-07-28"]


def test_analysis_params_are_prefixed():
    """분석 파라미터는 p_ 접두어로 다른 상태와 안 섞인다."""
    state = {**DEFAULTS, "analysis": "path_ranking", "params": {"n": 4}}
    encoded = encode_state(state)
    assert encoded["p_n"] == "4"
    assert decode_state(encoded)["params"] == {"n": 4}


def test_unknown_keys_are_ignored():
    """URL 에 손댄 낯선 키는 조용히 무시한다 — 화면을 안 깨뜨린다."""
    got = decode_state({"analysis": "screen_flow", "garbage": "x"})
    assert got["analysis"] == "screen_flow"
    assert "garbage" not in got
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_state.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.state'`

- [ ] **Step 3: 구현**

`dashboard/state.py`:
```python
"""대시보드 상태 ↔ URL query params. 순수 함수 — Streamlit 을 모른다.

상태는 flat dict 다. 리스트(services)는 콤마, 날짜 범위(dates)는 콜론, 분석 파라미터는
`p_` 접두어로 인코딩한다. 알 수 없는 키는 디코딩에서 버려 손댄 URL 이 화면을 깨지 않는다.
"""
from __future__ import annotations

DEFAULTS: dict = {
    "mode": "single",
    "tab": "overview",
    "analysis": "session_trend",
    "dates": [],          # [] 이면 present_dates 전체 (filters 에서 채움)
    "services": [],       # [] 이면 빌드된 전체
    "service_type": "",   # "" 이면 전체 (필터 안 함)
    "app_version": "",
    "os": "",
    "gender": "",
    "age_band": "",
    "daypart": "",
    "params": {},         # 분석별 파라미터
    "top": 10,
}

_LIST_KEYS = ("services",)
_RANGE_KEYS = ("dates",)
_INT_KEYS = ("top",)


def encode_state(state: dict) -> dict[str, str]:
    """상태 dict → query param 문자열 dict."""
    out: dict[str, str] = {}
    for key, default in DEFAULTS.items():
        if key == "params":
            for name, value in state.get("params", {}).items():
                out[f"p_{name}"] = str(value)
            continue
        value = state.get(key, default)
        if key in _LIST_KEYS or key in _RANGE_KEYS:
            sep = "," if key in _LIST_KEYS else ":"
            out[key] = sep.join(map(str, value))
        else:
            out[key] = str(value)
    return out


def decode_state(params: dict) -> dict:
    """query param dict → 상태 dict. 기본값을 채우고 타입을 복원한다."""
    state = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    state["params"] = {}
    for key, raw in params.items():
        if key.startswith("p_"):
            state["params"][key[2:]] = _coerce_param(raw)
        elif key in _LIST_KEYS:
            state[key] = [s for s in raw.split(",") if s]
        elif key in _RANGE_KEYS:
            state[key] = [s for s in raw.split(":") if s]
        elif key in _INT_KEYS:
            state[key] = int(raw)
        elif key in DEFAULTS:
            state[key] = raw
        # 그 외 낯선 키는 무시
    return state


def _coerce_param(raw: str):
    """파라미터 문자열을 int 로 되돌릴 수 있으면 되돌린다(예: n=4)."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_state.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add dashboard/state.py tests/dashboard/test_state.py
git commit -m "feat(dashboard): url state encode/decode with round-trip tests"
```

---

### Task 2: `params.py` — 분석별 파라미터 스펙

각 분석이 어떤 입력을 받는지 선언한다. `app.py` 가 이걸 읽어 사이드바 위젯을 동적으로 만든다. 스펙 표(설계 문서 "분석별 파라미터")를 그대로 옮긴다.

**Files:**
- Create: `dashboard/params.py`
- Test: `tests/dashboard/test_params.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/dashboard/test_params.py`:
```python
from dashboard.params import Param, params_for, required_names


def test_path_ranking_requires_n():
    specs = params_for("path_ranking")
    assert specs == [Param("n", "int", required=True)]
    assert required_names("path_ranking") == ["n"]


def test_reachability_requires_source_and_target():
    names = [p.name for p in params_for("reachability")]
    assert names == ["source", "target", "max_k"]
    assert required_names("reachability") == ["source", "target"]


def test_click_distribution_has_a_choice():
    (by,) = params_for("click_distribution")
    assert by.name == "by" and by.kind == "choice"
    assert "action_kind" in by.choices


def test_analysis_with_no_params_returns_empty():
    assert params_for("markov_order_test") == []
    assert required_names("markov_order_test") == []


def test_unknown_analysis_returns_empty():
    assert params_for("does_not_exist") == []
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_params.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.params'`

- [ ] **Step 3: 구현**

`dashboard/params.py`:
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_params.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add dashboard/params.py tests/dashboard/test_params.py
git commit -m "feat(dashboard): per-analysis parameter specs"
```

---

### Task 3: `render.py` — AnalysisResult → 표시 구조

`AnalysisResult` 를 화면에 그릴 조각으로 바꾼다: headline 카드 목록, 표 slice, 봉투 요약. 전부 순수 변환.

**Files:**
- Create: `dashboard/render.py`
- Test: `tests/dashboard/test_render.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/dashboard/test_render.py`:
```python
import pandas as pd

from dashboard.render import headline_cards, table_slice, envelope_summary


def test_headline_cards_format_label_value():
    cards = headline_cards({"mean_expected_steps": 8.0829, "mean_exit_prob": 0.1407})
    assert cards == [
        ("mean_expected_steps", "8.08"),
        ("mean_exit_prob", "0.14"),
    ]


def test_headline_cards_skip_nan():
    """NaN headline(예: 슬라이스의 uv)은 카드로 내지 않는다."""
    cards = headline_cards({"sessions": 1000.0, "uv": float("nan")})
    assert cards == [("sessions", "1,000")]


def test_table_slice_takes_top_n():
    frame = pd.DataFrame({"x": range(50)})
    assert len(table_slice(frame, 10)) == 10
    assert len(table_slice(frame, 999)) == 50   # 최대는 프레임 크기


def test_table_slice_zero_or_negative_is_empty():
    frame = pd.DataFrame({"x": range(5)})
    assert len(table_slice(frame, 0)) == 0


def test_envelope_summary_pulls_the_key_fields():
    envelope = {
        "warnings": [{"check_name": "screens_lumped_into_other"}],
        "coverage": {"dwell": 0.565},
        "state_dict_version": "sd_2ab5",
        "present_dates": ["2026-07-14", "2026-07-28"],
    }
    got = envelope_summary(envelope)
    assert got["warnings"] == ["screens_lumped_into_other"]
    assert got["state_dict_version"] == "sd_2ab5"
    assert got["n_dates"] == 2
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_render.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.render'`

- [ ] **Step 3: 구현**

`dashboard/render.py`:
```python
"""AnalysisResult 를 화면 조각으로 바꾸는 순수 변환. Streamlit 을 모른다."""
from __future__ import annotations

import math

import pandas as pd


def headline_cards(headline: dict) -> list[tuple[str, str]]:
    """{키: float} → [(라벨, 표시문자열)]. NaN 은 건너뛴다."""
    cards = []
    for key, value in headline.items():
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        cards.append((key, _fmt(value)))
    return cards


def _fmt(value: float) -> str:
    """정수 같은 큰 수는 천단위 콤마, 소수는 2자리."""
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:.2f}"


def table_slice(frame: pd.DataFrame, top: int) -> pd.DataFrame:
    """상위 top 행. 0 이하면 빈 프레임, 프레임보다 크면 전체."""
    return frame.head(max(0, top))


def envelope_summary(envelope: dict) -> dict:
    """봉투에서 화면에 낼 핵심만 뽑는다."""
    return {
        "warnings": [w.get("check_name", "?") for w in envelope.get("warnings", [])],
        "coverage": envelope.get("coverage", {}),
        "state_dict_version": envelope.get("state_dict_version", "?"),
        "n_dates": len(envelope.get("present_dates", [])),
    }
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_render.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add dashboard/render.py tests/dashboard/test_render.py
git commit -m "feat(dashboard): AnalysisResult to display pieces"
```

---

### Task 4: `charts.py` — viz.kind 차트 데이터 준비

`AnalysisResult.viz.kind` 를 읽어 차트에 넘길 데이터를 만든다. `st.*` 호출은 없다 — app.py 가 반환값을 `st.bar_chart` 등에 넘긴다. `graph` 는 첫 계획서에서 표로 대체하므로 여기서 `"table"` 로 떨어뜨린다.

**Files:**
- Create: `dashboard/charts.py`
- Test: `tests/dashboard/test_charts.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/dashboard/test_charts.py`:
```python
import pandas as pd

from dashboard.charts import chart_kind, bar_data, line_data, heatmap_pivot


def test_chart_kind_reads_viz():
    assert chart_kind({"kind": "bar", "x": "state"}) == "bar"


def test_graph_falls_back_to_table_in_this_plan():
    """graph(networkx)는 3계획서. 지금은 표로."""
    assert chart_kind({"kind": "graph", "x": "state"}) == "table"


def test_missing_kind_is_table():
    assert chart_kind({}) == "table"


def test_bar_data_indexes_by_x_and_takes_top():
    frame = pd.DataFrame({"state": ["a", "b", "c"], "pagerank": [0.3, 0.5, 0.2]})
    series = bar_data(frame, x="state", y="pagerank", top=2)
    assert list(series.index) == ["a", "b"]
    assert list(series.values) == [0.3, 0.5]


def test_line_data_indexes_by_x():
    frame = pd.DataFrame({"period": ["d1", "d2"], "sessions": [10, 20]})
    out = line_data(frame, x="period")
    assert list(out.index) == ["d1", "d2"]
    assert "sessions" in out.columns


def test_heatmap_pivot_makes_from_by_to_grid():
    frame = pd.DataFrame({
        "from_state": ["a", "a", "b"],
        "to_state": ["a", "b", "a"],
        "cnt": [1, 2, 3],
    })
    grid = heatmap_pivot(frame, "from_state", "to_state", "cnt")
    assert grid.loc["a", "b"] == 2
    assert grid.loc["b", "a"] == 3
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_charts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.charts'`

- [ ] **Step 3: 구현**

`dashboard/charts.py`:
```python
"""viz.kind → 차트 데이터 준비. 순수 — st.* 호출 없음.

app.py 가 반환값을 st.bar_chart / st.line_chart / st.dataframe 에 넘긴다. graph 는 이
계획서에서 표로 대체하므로 chart_kind 가 "table" 로 떨어뜨린다.
"""
from __future__ import annotations

import pandas as pd

_SUPPORTED = {"bar", "line", "heatmap"}


def chart_kind(viz: dict) -> str:
    """그릴 차트 종류. 지원 안 하는 kind(graph 등)는 표로."""
    kind = viz.get("kind", "table")
    return kind if kind in _SUPPORTED else "table"


def bar_data(frame: pd.DataFrame, x: str, y: str, top: int) -> pd.Series:
    """x 를 인덱스로, y 를 값으로 하는 상위 top 시리즈."""
    return frame.head(max(0, top)).set_index(x)[y]


def line_data(frame: pd.DataFrame, x: str) -> pd.DataFrame:
    """x 를 인덱스로 하는 프레임(수치 열 전부를 선으로)."""
    return frame.set_index(x)


def heatmap_pivot(frame: pd.DataFrame, from_col: str, to_col: str,
                  value: str) -> pd.DataFrame:
    """(from, to) 격자. 값은 value 열."""
    return frame.pivot_table(index=from_col, columns=to_col, values=value,
                             aggfunc="sum", fill_value=0)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_charts.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add dashboard/charts.py tests/dashboard/test_charts.py
git commit -m "feat(dashboard): viz.kind chart data preparation"
```

---

### Task 5: `filters.py` — 세그먼트 → CubeSet

세그먼트 dict 를 받아 필요한 큐브만 로드하고 축으로 좁힌다. 행동층 분석은 `path`·`action`·`cond_transition` 이 필요하므로 큐브 목록을 분석에 맞춰 고른다.

**Files:**
- Create: `dashboard/filters.py`
- Test: `tests/dashboard/test_filters.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/dashboard/test_filters.py`:
```python
import pandas as pd

from analytics.analyses.base import CubeSet
from dashboard.filters import cube_names_for, apply_segment


def test_cube_names_for_screen_analysis_is_default():
    from analytics.analyses.cubes import DEFAULT_CUBE_NAMES
    assert cube_names_for("screen_flow") == DEFAULT_CUBE_NAMES


def test_cube_names_for_action_analysis_includes_path():
    names = cube_names_for("path_ranking")
    assert "path" in names
    assert "transition" in names   # markov 는 transition 도 쓴다 → 전부 싣는다


def _cubes() -> CubeSet:
    edges = pd.DataFrame({
        "from_state": ["a", "a"], "to_state": ["b", "b"], "cnt": [1, 2],
        "service_type": ["MA", "MW"], "period": ["2026-07-27", "2026-07-27"],
    })
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def test_apply_segment_filters_axes_that_are_set():
    got = apply_segment(_cubes(), {"service_type": "MA", "os": ""})
    assert set(got.transition["service_type"]) == {"MA"}


def test_apply_segment_ignores_empty_axes():
    got = apply_segment(_cubes(), {"service_type": "", "os": ""})
    assert len(got.transition) == 2   # 아무것도 안 좁힘
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_filters.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.filters'`

- [ ] **Step 3: 구현**

`dashboard/filters.py`:
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard/test_filters.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add dashboard/filters.py tests/dashboard/test_filters.py
git commit -m "feat(dashboard): segment to CubeSet loading"
```

---

### Task 6: `app.py` — Streamlit 통합 (단일 모드)

앞의 순수 함수들을 Streamlit 위젯으로 엮는다. 이 파일만 `st.*` 를 부르고 자동 테스트가 없다 — 얇게 유지하고 수동 스모크로 확인한다.

**Files:**
- Create: `dashboard/app.py`
- Create: `.claude/launch.json`

- [ ] **Step 1: app.py 작성**

`dashboard/app.py`:
```python
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
```

- [ ] **Step 2: launch.json 작성 (Browser 미리보기용)**

`.claude/launch.json`:
```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "dashboard",
      "runtimeExecutable": ".venv/bin/streamlit",
      "runtimeArgs": ["run", "dashboard/app.py", "--server.headless", "true"],
      "port": 8501
    }
  ]
}
```

- [ ] **Step 3: import 스모크 (문법·임포트 확인)**

Run: `PYTHONPATH=. .venv/bin/python -c "import dashboard.app"`
Expected: 출력 없음, exit 0 (임포트 에러 없음)

- [ ] **Step 4: 전체 대시보드 유닛 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/dashboard -q`
Expected: PASS (앞 4개 테스트 파일 전부)

- [ ] **Step 5: 수동 스모크 (사람이 확인)**

Run: `PYTHONPATH=. .venv/bin/streamlit run dashboard/app.py`
브라우저에서 확인:
- 상단 모드 라디오(개요/화면흐름/행동/서비스/품질)가 뜬다
- 화면흐름 탭 → screen_flow 선택 → headline 카드·표·바 차트·봉투가 그려진다
- 표시 개수를 바꾸면 표 행 수가 바뀐다
- 행동 탭 → path_ranking → n 을 비우면 "필수 파라미터" 경고, 4 를 넣으면 그려진다
- 브라우저 주소창 URL 을 복사해 새 탭에 붙이면 같은 화면이 뜬다

- [ ] **Step 6: 커밋**

```bash
git add dashboard/app.py .claude/launch.json
git commit -m "feat(dashboard): streamlit single-mode app wiring the analyses"
```

---

### Task 7: 실행 문서 + 최종 스위트

**Files:**
- Create: `dashboard/README.md`

- [ ] **Step 1: README 작성**

`dashboard/README.md`:
```markdown
# 대시보드 (단일 모드)

    PYTHONPATH=. .venv/bin/streamlit run dashboard/app.py

숫자는 전부 `analytics/analyses/` 에서 온다 — 대시보드는 세그먼트·파라미터를 받아
분석을 부르고 그린다. 상태는 URL 에 있어 주소를 공유하면 같은 화면이 재현된다.

설계: `docs/superpowers/specs/2026-08-04-dashboard-design.md`
비교 모드는 둘째 계획서, graph 렌더는 셋째 계획서다.
```

- [ ] **Step 2: 전체 스위트가 안 깨졌는지 확인**

Run: `find . -path ./.venv -prune -o -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider`
Expected: 기존 824 passed + dashboard 유닛 추가분 전부 통과

- [ ] **Step 3: 커밋**

```bash
git add dashboard/README.md
git commit -m "docs(dashboard): run instructions"
```

---

## Self-Review

**1. Spec coverage (설계 문서 대비):**
- 위계(단일/비교, 탭) → Task 6 `main`·`TABS`. (비교는 둘째 계획서, 여기선 단일만)
- 세그먼트 필터 → Task 5 `filters.py` + Task 6 `_sidebar`
- 분석별 파라미터 동적 → Task 2 `params.py` + Task 6 `_sidebar`
- 표시 개수 입력(최대 안내) → Task 6 `number_input` + `st.caption` 전체 개수
- 시각화 viz.kind → Task 4 `charts.py` + Task 6 `_draw`
- 공유=URL → Task 1 `state.py` + Task 6 `query_params`
- 봉투 표시 → Task 3 `envelope_summary` + Task 6 `_draw`
- graph 표 대체 → Task 4 `chart_kind` → "table"
- 파일 구조 6파일 → Task 1~6 (compare_view 는 둘째 계획서)

**2. Placeholder scan:** 각 코드 step 에 완전한 코드가 있음. "TODO"/"적절히" 없음.

**3. Type consistency:** `apply_segment(cubes, segment)`·`load_for(config, segment, analysis, state_dict_version)`·`cube_names_for(analysis)`·`params_for`/`required_names`·`headline_cards`/`table_slice`/`envelope_summary`·`chart_kind`/`bar_data(frame,x,y,top)`/`line_data(frame,x)`/`heatmap_pivot(frame,from_col,to_col,value)` — Task 6 의 호출과 시그니처가 일치.

**주의(구현자에게):** `_draw` 의 heatmap 분기는 `cnt` 열을 가정한다. `conditional_flow`·`screen_pair_affinity`·`cross_service_flow` 는 `cnt` 를 갖지만, 값 열이 다른 분석이 heatmap 을 쓰게 되면 `viz` 에 값 열을 실어야 한다 — 지금 4종은 안전.

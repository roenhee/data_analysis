# 백엔드 API 골격 (1단계-A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `analyses/` 를 그대로 호출하는 FastAPI 백엔드 골격을 세운다 — `GET /api/meta` 와
`GET /api/analysis/session_trend` 가 올바른 JSON 을 반환하고, cube_store 가 선택 기간만 로드해
LRU 로 공유하며 기간 상한을 강제한다.

**Architecture:** 표현 계층만 추가한다. 숫자는 `analytics/analyses/` 가 만든다(불변 원칙).
`api/cube_store.py` 가 날짜 파티션 parquet 를 **선택 기간만** `load_cube_set` 으로 읽어
`functools.lru_cache` 로 공유하고 소프트(31일)/절대(90일) 상한을 건다. `api/analysis.py` 가
`AnalysisResult` 를 `{headline,columns,rows,viz,envelope}` JSON 으로 직렬화하며, `charts.py` 의
Altair 차트를 `.to_dict()` 로 Vega-Lite 스펙으로 바꿔 `viz` 에 싣는다. `api/meta.py` 가 분석
카탈로그·세그먼트 축·`present_dates`/`present_services` 를 조립한다. `dashboard/` 의 순수 모듈
(`charts`·`glossary`·`params`·`render`·`filters`)은 `st` 의존이 없으므로 **그대로 import 해서
재사용**한다(streamlit 폐기는 프론트 완성 후 4단계에서).

**Tech Stack:** Python 3, FastAPI, uvicorn, pandas, altair(Vega-Lite 생성기), pytest,
Starlette TestClient(FastAPI 내장).

---

## 실행 노트 (엔지니어가 먼저 읽을 것)

- **작업 디렉토리**: 프로젝트 루트 `/Users/roen.axz-pc/Desktop/projects/data_analysis`.
- **가상환경**: `.venv/bin/python`, `.venv/bin/pytest`, `.venv/bin/uvicorn`.
- **큐브는 로컬에 이미 있다** (`cache/cubes/`). `load_cube_set` 은 **Trino 를 건드리지 않는다**
  (`analytics/analyses/cubes.py` 참고) — 로컬 parquet + state_dict 만 읽는다. `dashboard/app.py`
  가 이 경로로 로컬에서 동작했으므로 같은 `Config.from_env()` 로 큐브가 로드된다.
- **⚠ 크레덴셜(project-roadmap 메모리)**: `Config.from_env()` 가 env 값을 요구해 테스트가 막히면,
  `$()` 로 비밀을 셸에 끌어내지 말고 아래 형태로 실행한다(설정을 바꾸자고 제안하지 말 것 —
  사용자가 "설정된 대로 하라"고 명시했다):
  ```bash
  .venv/bin/python -c '
  import sys, os; sys.path.insert(0, ".")
  import env
  for k in ("TIARA_ID", "TIARA_PW"):
      if hasattr(env, k): os.environ[k] = getattr(env, k)
  import pytest; raise SystemExit(pytest.main(["tests/api/", "-v"]))
  '
  ```
  먼저 크레덴셜 없이 `.venv/bin/pytest tests/api/ -v` 를 시도하고, `Config.from_env()` 에서
  막힐 때만 위 패턴을 쓴다.
- **정본 빌드**: `STATE_DICT_VERSION = "sd_2ab5ec25e750dda2"`(6서비스 15일, 현재 유일한 완성본).
  `SERVICES = ["top","media","entertain","sports","content_v","search"]`. (agorax 7서비스는 미완이라
  정본이 아니다 — spec 2026-08-06 "정본 빌드 선택" 참고.)
- **서버 실행(수동 스모크)**: `.venv/bin/uvicorn api.main:app --reload --port 8000`.

## File Structure

| 파일 | 책임 |
|---|---|
| Create `api/__init__.py` | 빈 패키지 마커 |
| Create `api/cube_store.py` | 선택 기간 로드 + LRU 캐시 + 기간 상한(소프트/절대). analyses 불변. |
| Create `api/analysis.py` | `AnalysisResult` → JSON, viz → Vega-Lite 스펙, 분석 실행 배선 |
| Create `api/meta.py` | 분석 카탈로그·세그먼트 축·present_dates/services 조립 |
| Create `api/main.py` | FastAPI 앱·라우팅·쿼리 파싱·에러 매핑 |
| Create `tests/api/__init__.py` | 테스트 패키지 마커 |
| Create `tests/api/test_cube_store.py` | 기간 계산·상한·LRU·실제 로드 |
| Create `tests/api/test_analysis.py` | JSON 직렬화·Vega-Lite viz·실제 session_trend |
| Create `tests/api/test_meta.py` | 카탈로그·축·present_dates |
| Create `tests/api/test_main.py` | 라우팅·400/404·통합 |

각 파일은 단일 책임. `api/` 는 `dashboard/` 순수 모듈을 import 하되 `st` 는 절대 import 하지 않는다
(API 가 streamlit 무게를 지지 않도록).

---

## Task 1: cube_store — 선택 기간 로드 + LRU + 기간 상한

**Files:**
- Create: `api/__init__.py`
- Create: `api/cube_store.py`
- Create: `tests/api/__init__.py`
- Test: `tests/api/test_cube_store.py`

- [ ] **Step 1: 빈 패키지 마커 생성**

`api/__init__.py` 와 `tests/api/__init__.py` 를 빈 파일로 만든다.

```bash
mkdir -p api tests/api && touch api/__init__.py tests/api/__init__.py
```

- [ ] **Step 2: 기간 계산·상한 실패 테스트 작성**

`tests/api/test_cube_store.py`:

```python
"""cube_store: 기간 계산·상한·LRU·실제 로드."""
import pytest

from api import cube_store


def test_period_days_counts_inclusive():
    assert cube_store.period_days("2026-07-14", "2026-07-14") == 1
    assert cube_store.period_days("2026-07-14", "2026-07-28") == 15


def test_load_rejects_over_hard_limit():
    with pytest.raises(cube_store.PeriodTooLongError):
        cube_store.load(("session",), "2026-01-01", "2026-12-31",
                        ("top",), "sd_2ab5ec25e750dda2")
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `.venv/bin/pytest tests/api/test_cube_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.cube_store'`

- [ ] **Step 4: cube_store 구현**

`api/cube_store.py`:

```python
"""큐브 로드 + LRU 캐시 + 기간 상한. analyses/ 는 건드리지 않는다.

날짜 파티션 parquet 를 **선택 기간만** 읽어(load_cube_set 이 요청 날짜만 로드) lru_cache 로
프로세스에 공유한다 — 동시 사용자가 늘어도 큐브는 한 벌이라 메모리가 일정하다(읽기 전용 공유).
소프트 상한(31일)은 막지 않고 경고(analysis.py 가 envelope 에 싣는다), 절대 상한(90일)은
거부한다(경고를 무시한 거대 조회의 OOM 최후 방어선).
"""
from __future__ import annotations

import functools
from datetime import date

from analytics.analyses.base import CubeSet
from analytics.analyses.cubes import load_cube_set
from dashboard.filters import expand_dates  # 순수 함수 재사용(st 의존 없음)
from data_layer.config import Config

SOFT_LIMIT_DAYS = 31   # 초과 시 경고(막지 않음)
HARD_LIMIT_DAYS = 90   # 초과 시 거부(OOM 방어)


class PeriodTooLongError(ValueError):
    """절대 상한을 넘는 기간 요청. 라우터가 400 으로 매핑한다."""


def period_days(start: str, end: str) -> int:
    """[start, end] 양끝 포함 일수."""
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


@functools.lru_cache(maxsize=8)
def _load_cached(
    cube_names: tuple[str, ...], start: str, end: str,
    services: tuple[str, ...], state_dict_version: str,
) -> CubeSet:
    """실제 로드. 인자가 전부 해시 가능(튜플·문자열)이라 lru_cache 키가 된다."""
    return load_cube_set(
        Config.from_env(),
        dates=expand_dates([start, end]),
        services=list(services),
        state_dict_version=state_dict_version,
        cube_names=cube_names,
    )


def load(
    cube_names, start: str, end: str, services, state_dict_version: str,
) -> CubeSet:
    """기간 상한을 검사하고 캐시된 로드를 부른다."""
    days = period_days(start, end)
    if days > HARD_LIMIT_DAYS:
        raise PeriodTooLongError(
            f"기간 {days}일이 절대 상한 {HARD_LIMIT_DAYS}일을 넘습니다 — "
            "메모리 보호를 위해 좁혀서 조회하세요."
        )
    return _load_cached(
        tuple(cube_names), start, end, tuple(services), state_dict_version
    )
```

- [ ] **Step 5: 기간 계산·상한 테스트 통과 확인**

Run: `.venv/bin/pytest tests/api/test_cube_store.py -v`
Expected: PASS (2개). `test_load_rejects_over_hard_limit` 은 상한 검사가 로드 **전에**
일어나므로 큐브·크레덴셜 없이도 통과한다.

- [ ] **Step 6: 실제 로드·LRU 테스트 추가**

`tests/api/test_cube_store.py` 에 덧붙인다:

```python
def test_load_reads_local_session_cube():
    cubes = cube_store.load(("session",), "2026-07-14", "2026-07-16",
                            ("top", "media", "entertain", "sports",
                             "content_v", "search"), "sd_2ab5ec25e750dda2")
    assert cubes.session is not None
    assert set(cubes.present_dates) <= {"2026-07-14", "2026-07-15", "2026-07-16"}
    assert cubes.state_dict_version == "sd_2ab5ec25e750dda2"


def test_load_is_cached_same_object():
    args = (("session",), "2026-07-14", "2026-07-16",
            ("top", "media", "entertain", "sports", "content_v", "search"),
            "sd_2ab5ec25e750dda2")
    assert cube_store.load(*args) is cube_store.load(*args)
```

- [ ] **Step 7: 실제 로드 테스트 실행**

Run: `.venv/bin/pytest tests/api/test_cube_store.py -v`
Expected: PASS (4개). 크레덴셜에서 막히면 실행 노트의 `.venv/bin/python -c 'import env…'`
패턴으로 재실행.

- [ ] **Step 8: 커밋**

```bash
git add api/__init__.py api/cube_store.py tests/api/__init__.py tests/api/test_cube_store.py
git commit -m "feat(api): cube_store — selected-period load, LRU cache, period limits"
```

---

## Task 2: analysis — AnalysisResult → JSON + Vega-Lite viz

**Files:**
- Create: `api/analysis.py`
- Test: `tests/api/test_analysis.py`

- [ ] **Step 1: JSON 직렬화 실패 테스트 작성 (합성 결과)**

`tests/api/test_analysis.py`:

```python
"""analysis: JSON 직렬화·Vega-Lite viz·실제 실행."""
import math

import pandas as pd

from analytics.analyses.base import AnalysisResult
from api import analysis


def _synthetic_line_result():
    frame = pd.DataFrame({
        "period": ["2026-07-14", "2026-07-15"],
        "sessions": [100, 120],
        "seconds_per_session": [10.5, float("nan")],
    })
    return AnalysisResult(
        frame=frame,
        headline={"sessions": 220.0, "seconds_per_session": float("nan")},
        envelope={"warnings": [], "coverage": {}, "present_dates":
                  ["2026-07-14", "2026-07-15"], "state_dict_version": "sd_x"},
        compare_key="period",
        viz={"kind": "line", "x": "period"},
    )


def test_result_to_json_shape():
    out = analysis.result_to_json(_synthetic_line_result(), period_days_value=2)
    assert {"headline", "columns", "rows", "viz", "envelope"} <= set(out)
    # headline: NaN 은 render.headline_cards 가 건너뛰므로 sessions 만 남는다.
    labels = [h["label"] for h in out["headline"]]
    assert any("sessions" in lbl or "세션" in lbl for lbl in labels)
    # rows: NaN → None 으로 직렬화(JSON 안전).
    assert out["rows"][1][2] is None
    assert out["envelope"]["period_days"] == 2


def test_result_to_json_soft_limit_warning():
    out = analysis.result_to_json(_synthetic_line_result(), period_days_value=40)
    assert any("한 달" in w for w in out["envelope"]["warnings"])


def test_vega_spec_line_is_vega_lite_dict():
    spec = analysis.vega_spec(_synthetic_line_result())
    assert spec["mark"]["type"] == "line" or spec.get("mark") == "line" \
        or spec["mark"]["type"] == "line"
    assert "encoding" in spec
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/pytest tests/api/test_analysis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.analysis'`

- [ ] **Step 3: analysis 구현**

`api/analysis.py`:

```python
"""AnalysisResult → JSON. viz 를 Vega-Lite 스펙으로.

숫자는 만들지 않는다 — get_analysis 결과를 프론트가 먹을 JSON 으로 바꿀 뿐이다.
charts.py 의 Altair 는 이미 Vega-Lite 생성기라 .to_dict() 로 스펙을 얻는다.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from analytics.analyses.base import AnalysisResult, get_analysis
from dashboard import charts, filters, glossary, params, render
from api import cube_store

CHART_TOP = 20   # 차트에 그릴 상위 개수(막대 수천 개 방지). 표는 전량.


def _json_safe(value):
    """numpy/NaN/inf 를 JSON 안전 값으로. 표준 json 은 numpy 를 못 낸다."""
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def vega_spec(result: AnalysisResult, chart_top: int = CHART_TOP):
    """viz.kind → Vega-Lite dict. graph 는 별도 형태, 지원 안 하면 None(표만)."""
    viz = result.viz or {}
    frame = result.frame
    if viz.get("kind") == "graph":
        # 1단계 골격엔 graph 분석이 없다(session_trend=line). 형태만 유지.
        return {"kind": "graph", "x": viz.get("x", "state"),
                "edges": viz.get("edges", [])}
    kind = charts.chart_kind(viz)
    x = viz.get("x")
    if kind == "line" and x in frame.columns:
        return charts.line_chart(frame, x).to_dict()
    if kind == "bar" and x in frame.columns:
        y = next((c for c in frame.columns
                  if pd.api.types.is_numeric_dtype(frame[c])), None)
        if y:
            return charts.bar_chart(frame, x, y, chart_top).to_dict()
    if kind == "heatmap":
        to = "to_state" if "to_state" in frame.columns else "to_service"
        return charts.heatmap_chart(frame, x, to, viz.get("value", "cnt")).to_dict()
    return None


def result_to_json(result: AnalysisResult, period_days_value: int | None = None) -> dict:
    """AnalysisResult → {headline, columns, rows, viz, envelope}."""
    cards = render.headline_cards(result.headline)
    headline = [
        {"label": glossary.metric_label(key), "value": shown,
         "help": glossary.metric_help(key) or None}
        for key, shown in cards
    ]
    columns = [
        {"key": c, "label": glossary.column_label(c),
         "help": glossary.column_help(c) or None}
        for c in result.frame.columns
    ]
    rows = [[_json_safe(v) for v in row]
            for row in result.frame.to_numpy().tolist()]

    env = render.envelope_summary(result.envelope)
    warnings = [glossary.warning_label(w) for w in env["warnings"]]
    if period_days_value is not None and period_days_value > cube_store.SOFT_LIMIT_DAYS:
        warnings.append("기간이 한 달을 넘어 느릴 수 있습니다")
    envelope = {
        "warnings": warnings,
        "state_dict_version": env["state_dict_version"],
        "n_dates": env["n_dates"],
        "period_days": period_days_value,
    }
    return {"headline": headline, "columns": columns, "rows": rows,
            "viz": vega_spec(result), "envelope": envelope}


def run_analysis(name: str, start: str, end: str, segment: dict,
                 param_values: dict, state_dict_version: str) -> dict:
    """cube_store 로드 → 축 필터 → coerce → 분석 호출 → JSON."""
    cubes = cube_store.load(
        tuple(sorted(filters.cube_names_for(name))),
        start, end, tuple(segment["services"]), state_dict_version,
    )
    cubes = filters.apply_segment(cubes, segment)
    call_params = params.coerce(name, param_values)
    result = get_analysis(name)(cubes, **call_params)
    return result_to_json(result, period_days_value=cube_store.period_days(start, end))
```

- [ ] **Step 4: 합성 직렬화 테스트 통과 확인**

Run: `.venv/bin/pytest tests/api/test_analysis.py -v`
Expected: PASS (3개). 합성 결과라 큐브·크레덴셜 불필요.

- [ ] **Step 5: 실제 session_trend 실행 테스트 추가**

`tests/api/test_analysis.py` 에 덧붙인다:

```python
_SERVICES = ("top", "media", "entertain", "sports", "content_v", "search")


def test_run_session_trend_real_cube():
    out = analysis.run_analysis(
        "session_trend", "2026-07-14", "2026-07-16",
        {"services": list(_SERVICES)}, {}, "sd_2ab5ec25e750dda2")
    # headline 에 세션 수가 있고, viz 는 라인 차트 스펙이다.
    assert out["headline"], "headline 이 비면 안 된다"
    assert out["viz"]["encoding"]["x"] is not None
    assert len(out["rows"]) >= 1
```

- [ ] **Step 6: 실제 실행 테스트 통과 확인**

Run: `.venv/bin/pytest tests/api/test_analysis.py -v`
Expected: PASS (4개). 크레덴셜에서 막히면 실행 노트 패턴으로.

- [ ] **Step 7: 커밋**

```bash
git add api/analysis.py tests/api/test_analysis.py
git commit -m "feat(api): analysis — AnalysisResult to JSON, Altair to Vega-Lite viz"
```

---

## Task 3: meta — 분석 카탈로그·세그먼트 축·present_dates

**Files:**
- Create: `api/meta.py`
- Test: `tests/api/test_meta.py`

- [ ] **Step 1: meta 실패 테스트 작성**

`tests/api/test_meta.py`:

```python
"""meta: 카탈로그·세그먼트 축·present_dates."""
from api import meta


def test_build_meta_has_catalog_and_axes():
    m = meta.build_meta()
    names = [a["name"] for a in m["analyses"]]
    assert "session_trend" in names
    # 한글 라벨이 붙는다.
    st_entry = next(a for a in m["analyses"] if a["name"] == "session_trend")
    assert st_entry["label"] and st_entry["label"] != "session_trend"
    # 세그먼트 축 6개.
    axes = [s["axis"] for s in m["segments"]]
    assert set(axes) == {"service_type", "app_version", "os",
                         "gender", "age_band", "daypart"}
    # 파라미터 있는 분석은 params 를 싣는다.
    flow = next(a for a in m["analyses"] if a["name"] == "screen_flow")
    assert any(p["name"] == "damping" for p in flow["params"])


def test_build_meta_present_dates_and_services():
    m = meta.build_meta()
    assert m["present_dates"], "빌드된 날짜가 있어야 한다"
    assert "2026-07-14" in m["present_dates"]
    assert set(m["present_services"]) >= {"top", "search"}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/pytest tests/api/test_meta.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.meta'`

- [ ] **Step 3: meta 구현**

`api/meta.py`:

```python
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
```

- [ ] **Step 4: meta 테스트 통과 확인**

Run: `.venv/bin/pytest tests/api/test_meta.py -v`
Expected: PASS (2개). `_segments`·`_present_dates` 가 실제 큐브를 읽으므로 크레덴셜에서
막히면 실행 노트 패턴으로.

- [ ] **Step 5: 커밋**

```bash
git add api/meta.py tests/api/test_meta.py
git commit -m "feat(api): meta — analysis catalog, segment axes, present dates/services"
```

---

## Task 4: main — FastAPI 라우팅·에러 매핑·통합

**Files:**
- Create: `api/main.py`
- Test: `tests/api/test_main.py`

- [ ] **Step 1: 라우팅 실패 테스트 작성**

`tests/api/test_main.py`:

```python
"""main: 라우팅·400/404·통합."""
from starlette.testclient import TestClient

from api.main import app

client = TestClient(app)
_SEG = "&".join(f"{a}=" for a in ())  # 세그먼트 없이 조회


def test_meta_endpoint():
    r = client.get("/api/meta")
    assert r.status_code == 200
    assert "session_trend" in [a["name"] for a in r.json()["analyses"]]


def test_analysis_endpoint_session_trend():
    r = client.get("/api/analysis/session_trend",
                   params={"start": "2026-07-14", "end": "2026-07-16"})
    assert r.status_code == 200
    body = r.json()
    assert body["headline"]
    assert body["viz"]["encoding"]["x"] is not None


def test_missing_required_param_is_400():
    # path_ranking 은 n(required)이 필요하다.
    r = client.get("/api/analysis/path_ranking",
                   params={"start": "2026-07-14", "end": "2026-07-16"})
    assert r.status_code == 400
    assert "n" in r.text


def test_period_over_hard_limit_is_400():
    r = client.get("/api/analysis/session_trend",
                   params={"start": "2026-01-01", "end": "2026-12-31"})
    assert r.status_code == 400


def test_unknown_analysis_is_404():
    r = client.get("/api/analysis/no_such_analysis",
                   params={"start": "2026-07-14", "end": "2026-07-16"})
    assert r.status_code == 404
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/pytest tests/api/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.main'`

- [ ] **Step 3: main 구현**

`api/main.py`:

```python
"""FastAPI 앱: /api/meta, /api/analysis/{name}.

숫자는 만들지 않는다 — 요청을 파싱해 analysis.run_analysis 로 넘기고 결과 JSON 을 낸다.
세그먼트 축은 반복 쿼리(?os=android&os=ios), 파라미터는 그 밖의 쿼리다.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from analytics.analyses.base import UnknownAnalysisError
from dashboard import filters, params
from api import analysis, cube_store, meta

app = FastAPI(title="Markov 대시보드 API")

# 사내망 개발용. vite dev proxy 를 쓰면 동일 출처라 실제로는 불필요하나, 직접 호출도 열어둔다.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/meta")
def get_meta():
    return meta.build_meta()


@app.get("/api/analysis/{name}")
def get_analysis_result(name: str, request: Request, start: str, end: str):
    # 세그먼트 축은 반복 쿼리로 받는다(multiselect).
    segment = {"services": meta.SERVICES, "dates": [start, end]}
    for axis in filters.SEGMENT_AXES:
        values = request.query_params.getlist(axis)
        if values:
            segment[axis] = values

    # 나머지 쿼리는 분석 파라미터.
    reserved = {"start", "end"} | set(filters.SEGMENT_AXES)
    param_values = {k: v for k, v in request.query_params.items() if k not in reserved}

    missing = [n for n in params.required_names(name) if n not in param_values]
    if missing:
        raise HTTPException(400, f"필수 파라미터를 선택하세요: {', '.join(missing)}")

    try:
        return analysis.run_analysis(
            name, start, end, segment, param_values, meta.STATE_DICT_VERSION)
    except cube_store.PeriodTooLongError as exc:
        raise HTTPException(400, str(exc)) from exc
    except UnknownAnalysisError as exc:
        raise HTTPException(404, str(exc)) from exc
```

- [ ] **Step 4: 라우팅 테스트 통과 확인**

Run: `.venv/bin/pytest tests/api/test_main.py -v`
Expected: PASS (5개). 크레덴셜에서 막히면 실행 노트 패턴으로.

- [ ] **Step 5: 전체 api 테스트 실행**

Run: `.venv/bin/pytest tests/api/ -v`
Expected: PASS (전부, 15개 안팎). 기존 테스트 회귀 없음 확인: `.venv/bin/pytest -q`
(912 passed 유지 + api 추가분).

- [ ] **Step 6: 수동 스모크(서버 기동 + curl)**

Run:
```bash
.venv/bin/uvicorn api.main:app --port 8000 &
sleep 2
curl -s "http://localhost:8000/api/meta" | head -c 300
echo
curl -s "http://localhost:8000/api/analysis/session_trend?start=2026-07-14&end=2026-07-16" | head -c 300
kill %1
```
Expected: `/api/meta` 가 analyses/segments/present_dates 를 담은 JSON, `/api/analysis/…` 가
headline/rows/viz 를 담은 JSON.

- [ ] **Step 7: 커밋**

```bash
git add api/main.py tests/api/test_main.py
git commit -m "feat(api): FastAPI routing — /api/meta, /api/analysis/{name} with error mapping"
```

---

## Self-Review

**1. Spec coverage** (spec 2026-08-06 대비):
- 메모리 아키텍처(선택기간 로드+LRU+소프트/절대 상한) → Task 1 cube_store ✅
- analyses 불변, 순수모듈 재사용 → Task 2 (dashboard.charts/glossary/params/render/filters import) ✅
- viz Altair→Vega-Lite `.to_dict()` → Task 2 vega_spec ✅
- present_dates/services 자동 적응 → Task 3 meta (_present_dates require_complete=False) ✅
- 서비스 전체 고정(선택 UI 없음) → SERVICES 상수 고정, 축에 없음 ✅
- API 계약(meta/analysis 반환 형태) → Task 3·2·4 ✅
- 필수 파라미터 400 / 절대 상한 400 / 소프트 상한 경고 → Task 4·2 ✅
- **범위 밖(이 계획서)**: 프론트(scaffold·컴포넌트·react-vega), streamlit 폐기, graph 렌더,
  서버 페이지네이션 — 다음 계획서(1단계-B 프론트).

**2. Placeholder scan:** "TBD/TODO/적절히" 없음. 모든 코드 블록 완전. ✅

**3. Type consistency:**
- `cube_store.load(cube_names, start, end, services, state_dict_version)` — Task 1 정의, Task 2·3
  에서 같은 시그니처로 호출 ✅
- `cube_store.SOFT_LIMIT_DAYS`/`period_days`/`PeriodTooLongError` — Task 1 정의, Task 2·4 참조 ✅
- `analysis.run_analysis(name, start, end, segment, param_values, state_dict_version)` — Task 2
  정의, Task 4 호출 일치 ✅
- `meta.SERVICES`/`meta.STATE_DICT_VERSION` — Task 3 정의, Task 4 참조 ✅
- `result_to_json` 반환 키(headline/columns/rows/viz/envelope) — Task 2 정의, Task 4 테스트가
  같은 키 확인 ✅
- `filters.SEGMENT_AXES`/`cube_names_for`/`apply_segment`, `params.required_names`/`coerce`,
  `glossary.*_label`, `render.headline_cards`/`envelope_summary` — 모두 기존 dashboard 모듈의
  실제 시그니처(이 세션에서 읽어 확인) ✅

**glossary 함수명 확인 완료:** `dashboard/glossary.py` 를 직접 확인해 `metric_label`·
`metric_help`·`column_label`·`column_help`·`analysis_label`·`analysis_desc`·`warning_label`·
`value_label`·`axis_label`·`axis_help`·`axis_value_label` 이 모두 존재함을 검증했다 — 계획서의
glossary 호출은 실제 시그니처와 일치한다.

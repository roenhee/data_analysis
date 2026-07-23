# Descriptive Analytics Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** markov와 분리된 on-demand 디스크립티브 분석 스킬을 만들어, 서버측 전수(비샘플) 집계로 절대 지표(기간별 UV/PV, 세션 engagement)를 계산하고 `publish_result`로 발행한다.

**Architecture:** `data_layer`에 범용 서버측 집계 프리미티브 `fetch_aggregate`(비샘플 실행 + content-hash 캐시) 하나만 추가한다. 지표 SQL·메뉴·검증·shaping·viz·publish는 신규 `skills/descriptive/` 패키지가 소유해 data_layer의 분석 비종속 경계를 유지한다. 세션 = `(app_user_id, isuid)`.

**Tech Stack:** Python 3, pandas, Trino DBAPI(서버 집계), parquet 캐시, pytest(TDD). 스펙: [docs/superpowers/specs/2026-07-23-descriptive-analytics-design.md](../specs/2026-07-23-descriptive-analytics-design.md).

---

## File Structure

**신규:**
- `data_layer/fetch_aggregate.py` — 서버측 전수 집계 실행 + 결과 캐시 프리미티브. `query_fn` seam으로 서버 I/O 주입 가능(테스트).
- `skills/__init__.py` — 빈 패키지 마커.
- `skills/descriptive/__init__.py` — 빈 패키지 마커(순환 import 방지 위해 재-export 안 함; 소비자는 서브모듈 직접 import).
- `skills/descriptive/sql.py` — `build_uv_pv_sql`, `build_session_engagement_sql`, `BREAKDOWN_WHITELIST`.
- `skills/descriptive/run.py` — `run_analysis`(검증→SQL→fetch→shape→publish).
- `skills/descriptive/descriptor.py` — `DESCRIPTOR` + `register`.
- `tests/test_fetch_aggregate.py`, `tests/test_descriptive_sql.py`, `tests/test_descriptive_run.py`, `tests/test_descriptive_descriptor.py`
- `tests/integration/test_descriptive_live.py` — 실 Trino 스모크(creds 없으면 skip).

**수정:**
- `data_layer/__init__.py` — `fetch_aggregate` export.

**규약:** 테스트는 `config` fixture(conftest.py, tmp_path 기반)를 쓴다. `pytest.ini`에 `pythonpath = .`라 `skills`는 루트에서 import된다. 결과 id는 `content_hash(run_id, analysis_type, title)`로 결정적이므로 **한 run 안에서 결과를 구분하려면 title을 다르게** 준다.

---

## Task 1: `fetch_aggregate` 서버측 집계 프리미티브

**Files:**
- Create: `data_layer/fetch_aggregate.py`
- Modify: `data_layer/__init__.py`
- Test: `tests/test_fetch_aggregate.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_fetch_aggregate.py`:
```python
import pandas as pd

from data_layer.fetch_aggregate import fetch_aggregate
from data_layer.sources import SourceDef


def _src():
    return SourceDef(
        id="events", kind="trino", host="h", port=8443,
        catalog="c", schema="s", table="t", auth_ref="TIARA",
        column_map={"app_user_id": "user.app_user_id"},
    )


def test_fetch_aggregate_caches_and_skips_refetch(config):
    calls = {"n": 0}

    def fake_query(source, sql):
        calls["n"] += 1
        return pd.DataFrame({"period": ["2026-01-05"], "uv": [10]})

    df1 = fetch_aggregate(config, _src(), "SELECT 1", query_fn=fake_query)
    df2 = fetch_aggregate(config, _src(), "SELECT 1", query_fn=fake_query)
    assert calls["n"] == 1                 # 2회차는 캐시 히트
    assert list(df1["uv"]) == [10]
    assert list(df2["uv"]) == [10]


def test_fetch_aggregate_refresh_reruns(config):
    calls = {"n": 0}

    def fake_query(source, sql):
        calls["n"] += 1
        return pd.DataFrame({"uv": [calls["n"]]})

    fetch_aggregate(config, _src(), "SELECT 1", query_fn=fake_query)
    df = fetch_aggregate(config, _src(), "SELECT 1", refresh=True, query_fn=fake_query)
    assert calls["n"] == 2
    assert list(df["uv"]) == [2]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_fetch_aggregate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.fetch_aggregate'`

- [ ] **Step 3: 최소 구현**

`data_layer/fetch_aggregate.py`:
```python
from __future__ import annotations

import pandas as pd

from data_layer.config import Config
from data_layer.manifest import Manifest
from data_layer.sources import SourceDef
from data_layer.util import content_hash


def _default_query(source: SourceDef, sql: str) -> pd.DataFrame:
    """실 Trino 서버측 집계 실행 (I/O seam; 테스트에서 query_fn으로 대체)."""
    from data_layer.connection import connect

    conn = connect(source)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


def fetch_aggregate(
    config: Config,
    source: SourceDef,
    sql: str,
    refresh: bool = False,
    query_fn=None,
) -> pd.DataFrame:
    """서버측 전수(비샘플) 집계 SQL을 실행하고 결과를 content-hash로 캐시.

    캐시 키는 (sql, source.version())가 결정한다. 성공 시에만 캐시/색인한다.
    query_fn(source, sql) -> DataFrame 로 서버 I/O를 주입할 수 있다.
    """
    config.ensure_dirs()
    h = "agg_" + content_hash(sql, source.version())
    path = config.results_dir / f"{h}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)

    df = (query_fn or _default_query)(source, sql)
    df.to_parquet(path)

    m = Manifest.load(config.manifest_path)
    m.add_result(
        result_hash=h,
        source_summary=f"{source.id}:aggregate",
        date_range=[],
        params={},
        config_version="",
        rows=int(len(df)),
        size_bytes=int(path.stat().st_size),
    )
    m.save()
    return df
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_fetch_aggregate.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 공개 API export**

`data_layer/__init__.py` — import 블록에 추가:
```python
from data_layer.fetch_aggregate import fetch_aggregate
```
그리고 `__all__` 리스트에 `"fetch_aggregate",` 추가.

- [ ] **Step 6: 전체 스위트 회귀 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 기존 64 passed + 2 new = 66 passed, 3 skipped

- [ ] **Step 7: 커밋**

```bash
git add data_layer/fetch_aggregate.py data_layer/__init__.py tests/test_fetch_aggregate.py
git commit -m "feat: add fetch_aggregate server-side aggregate primitive"
```

---

## Task 2: `skills/descriptive` 패키지 + `build_uv_pv_sql`

**Files:**
- Create: `skills/__init__.py` (빈 파일), `skills/descriptive/__init__.py` (빈 파일)
- Create: `skills/descriptive/sql.py`
- Test: `tests/test_descriptive_sql.py`

- [ ] **Step 1: 빈 패키지 마커 생성**

`skills/__init__.py` 와 `skills/descriptive/__init__.py` 를 **빈 파일**로 생성한다(내용 없음). 재-export는 순환 import를 유발하므로 하지 않는다.

- [ ] **Step 2: 실패 테스트 작성**

`tests/test_descriptive_sql.py`:
```python
from data_layer.sources import SourceDef
from skills.descriptive.sql import build_uv_pv_sql


def _src():
    return SourceDef(
        id="events", kind="trino", host="h", port=8443,
        catalog="bigdata_omega_common_iceberg", schema="axz_tiara", table="all_tiara_i",
        auth_ref="TIARA",
        column_map={
            "action_type": "action.type",
            "app_user_id": "user.app_user_id",
            "isuid": "user.isuid",
            "access_time": "try_cast(common.access_time AS timestamp)",
            "app_version": "env.app_version",
            "usage_duration": "try(cast(usage.duration as double))",
        },
        filters=["action.type IN ('Pageview','Event')"],
    )


def test_uv_pv_sql_core_pieces():
    sql = build_uv_pv_sql(_src(), ("2026-01-05", "2026-02-01"), "day", [], {})
    assert "bigdata_omega_common_iceberg.axz_tiara.all_tiara_i" in sql
    assert "date_trunc('day', try_cast(common.access_time AS timestamp)) AS period" in sql
    assert "COUNT(DISTINCT user.app_user_id) AS uv" in sql
    assert "COUNT(*) FILTER (WHERE action.type = 'Pageview') AS pv" in sql
    assert "action.type IN ('Pageview','Event')" in sql          # 소스 base 필터 유지
    assert "2026-01-05 00:00:00" in sql and "2026-02-01 23:59:59" in sql
    assert "GROUP BY 1" in sql


def test_uv_pv_sql_breakdown_adds_dim_and_group():
    sql = build_uv_pv_sql(_src(), ("2026-01-05", "2026-02-01"), "week", ["app_version"], {})
    assert "date_trunc('week'," in sql
    assert "env.app_version AS app_version" in sql
    assert "GROUP BY 1, 2" in sql


def test_uv_pv_sql_filter_equality_is_escaped():
    sql = build_uv_pv_sql(_src(), ("2026-01-05", "2026-02-01"), "day", [], {"app_version": "10.5'x"})
    assert "env.app_version = '10.5''x'" in sql                   # 작은따옴표 이스케이프
```

- [ ] **Step 3: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_sql.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills.descriptive.sql'`

- [ ] **Step 4: 최소 구현**

`skills/descriptive/sql.py`:
```python
from __future__ import annotations

from data_layer.sources import SourceDef

# breakdown/filter로 허용되는 화이트리스트 컬럼 (저카디널리티 → 카디널리티 폭발 차단)
BREAKDOWN_WHITELIST = ("app_version", "os", "service_code")


def _col(source: SourceDef, flat: str, default: str) -> str:
    return source.column_map.get(flat, default)


def _table(source: SourceDef) -> str:
    return f"{source.catalog}.{source.schema}.{source.table}"


def _escape(value) -> str:
    return str(value).replace("'", "''")


def _where(source: SourceDef, window, filters: dict) -> str:
    start, end = window
    ts = _col(source, "access_time", "try_cast(common.access_time AS timestamp)")
    conds = ["1=1", *source.filters]
    conds.append(f"{ts} BETWEEN TIMESTAMP '{start} 00:00:00' AND TIMESTAMP '{end} 23:59:59'")
    for key, val in filters.items():
        conds.append(f"{_col(source, key, key)} = '{_escape(val)}'")
    return "\n      AND ".join(conds)


def _period_expr(source: SourceDef, grain: str) -> str:
    ts = _col(source, "access_time", "try_cast(common.access_time AS timestamp)")
    return f"date_trunc('{grain}', {ts})"


def _breakdown_selects(source: SourceDef, breakdown) -> list:
    return [f"{_col(source, b, b)} AS {b}" for b in breakdown]


def _assemble(select_lines: list, source: SourceDef, window, filters: dict, n_dims: int) -> str:
    group_by = ", ".join(str(n) for n in range(1, 2 + n_dims))   # period(+breakdown)
    return (
        "SELECT\n    " + ",\n    ".join(select_lines)
        + f"\nFROM {_table(source)}"
        + f"\nWHERE {_where(source, window, filters)}"
        + f"\nGROUP BY {group_by}\nORDER BY {group_by}\n"
    )


def build_uv_pv_sql(source: SourceDef, window, grain, breakdown, filters) -> str:
    au = _col(source, "app_user_id", "user.app_user_id")
    at = _col(source, "action_type", "action.type")
    lines = [
        f"{_period_expr(source, grain)} AS period",
        *_breakdown_selects(source, breakdown),
        f"COUNT(DISTINCT {au}) AS uv",
        f"COUNT(*) FILTER (WHERE {at} = 'Pageview') AS pv",
    ]
    return _assemble(lines, source, window, filters, len(breakdown))
```

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_sql.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋**

```bash
git add skills/__init__.py skills/descriptive/__init__.py skills/descriptive/sql.py tests/test_descriptive_sql.py
git commit -m "feat: add descriptive skill package and build_uv_pv_sql"
```

---

## Task 3: `build_session_engagement_sql` + UV 비가산성 가드

**Files:**
- Modify: `skills/descriptive/sql.py`
- Test: `tests/test_descriptive_sql.py` (테스트 추가)

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_descriptive_sql.py` 상단 import에 `build_session_engagement_sql` 추가:
```python
from skills.descriptive.sql import build_uv_pv_sql, build_session_engagement_sql
```
파일 끝에 테스트 추가:
```python
def test_session_engagement_sql_core_pieces():
    sql = build_session_engagement_sql(_src(), ("2026-01-05", "2026-02-01"), "day", [], {})
    assert (
        "COUNT(DISTINCT CAST(user.app_user_id AS VARCHAR) || '|' || "
        "CAST(user.isuid AS VARCHAR)) AS sessions"
    ) in sql
    assert "COUNT(DISTINCT user.app_user_id) AS uv" in sql
    assert "SUM(try(cast(usage.duration as double))) AS total_duration" in sql
    assert "GROUP BY 1" in sql


def test_uv_is_recomputed_per_grain_not_summed():
    # UV는 비가산적: 월 UV는 month grain에서 새로 COUNT(DISTINCT)해야 하며
    # 일별 UV의 SUM이면 안 된다. 카운트 합산 회귀를 막는 가드.
    month = build_uv_pv_sql(_src(), ("2026-01-01", "2026-03-31"), "month", [], {})
    assert "date_trunc('month'," in month
    assert "COUNT(DISTINCT user.app_user_id) AS uv" in month
    assert "SUM(" not in month              # 카운트 합산 없음
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_sql.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_session_engagement_sql'`

- [ ] **Step 3: 최소 구현**

`skills/descriptive/sql.py` 끝에 추가:
```python
def build_session_engagement_sql(source: SourceDef, window, grain, breakdown, filters) -> str:
    au = _col(source, "app_user_id", "user.app_user_id")
    isuid = _col(source, "isuid", "user.isuid")
    dur = _col(source, "usage_duration", "try(cast(usage.duration as double))")
    session_key = f"CAST({au} AS VARCHAR) || '|' || CAST({isuid} AS VARCHAR)"
    lines = [
        f"{_period_expr(source, grain)} AS period",
        *_breakdown_selects(source, breakdown),
        f"COUNT(DISTINCT {session_key}) AS sessions",
        f"COUNT(DISTINCT {au}) AS uv",
        f"SUM({dur}) AS total_duration",
    ]
    return _assemble(lines, source, window, filters, len(breakdown))
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_sql.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add skills/descriptive/sql.py tests/test_descriptive_sql.py
git commit -m "feat: add build_session_engagement_sql and UV non-additivity guard"
```

---

## Task 4: `run_analysis` — 검증 + uv_pv 발행

**Files:**
- Create: `skills/descriptive/run.py`
- Test: `tests/test_descriptive_run.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_descriptive_run.py`:
```python
import pandas as pd
import pytest

from data_layer.results import read_result
from data_layer.sources import SourceDef
from skills.descriptive.run import run_analysis


def _src():
    return SourceDef(
        id="events", kind="trino", host="h", port=8443,
        catalog="c", schema="s", table="t", auth_ref="TIARA",
        column_map={
            "action_type": "action.type",
            "app_user_id": "user.app_user_id",
            "isuid": "user.isuid",
            "access_time": "try_cast(common.access_time AS timestamp)",
            "app_version": "env.app_version",
            "usage_duration": "try(cast(usage.duration as double))",
        },
    )


def _fake_uv_pv(config, source, sql):
    return pd.DataFrame(
        {"period": ["2026-01-05", "2026-01-06"], "uv": [10, 12], "pv": [30, 40]}
    )


def test_run_uv_pv_publishes_contract_result(config):
    rid = run_analysis(
        config, _src(), "uv_pv_by_period",
        params={"window": ["2026-01-05", "2026-01-06"], "grain": "day"},
        run_id="r1", config_version="cfg1", aggregate_fetcher=_fake_uv_pv,
    )
    df, env = read_result(config, rid)
    assert list(df.columns) == ["period", "uv", "pv"]
    assert env["skill"] == "descriptive"
    assert env["analysis_type"] == "uv_pv_by_period"
    assert env["viz"]["chart_type"] == "line"
    assert "전수집계(비샘플)" in env["caveats"]


def test_run_rejects_unknown_analysis_type(config):
    with pytest.raises(ValueError, match="unknown analysis_type"):
        run_analysis(
            config, _src(), "nope", params={"window": ["a", "b"]},
            run_id="r", config_version="c", aggregate_fetcher=_fake_uv_pv,
        )


def test_run_rejects_bad_grain(config):
    with pytest.raises(ValueError, match="grain"):
        run_analysis(
            config, _src(), "uv_pv_by_period",
            params={"window": ["a", "b"], "grain": "fortnight"},
            run_id="r", config_version="c", aggregate_fetcher=_fake_uv_pv,
        )


def test_run_rejects_bad_breakdown(config):
    with pytest.raises(ValueError, match="whitelist"):
        run_analysis(
            config, _src(), "uv_pv_by_period",
            params={"window": ["a", "b"], "breakdown": ["evil_col"]},
            run_id="r", config_version="c", aggregate_fetcher=_fake_uv_pv,
        )
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills.descriptive.run'`

- [ ] **Step 3: 최소 구현**

`skills/descriptive/run.py`:
```python
from __future__ import annotations

from data_layer.fetch_aggregate import fetch_aggregate
from data_layer.results import publish_result
from skills.descriptive.sql import (
    BREAKDOWN_WHITELIST,
    build_uv_pv_sql,
)

MENU = ("uv_pv_by_period", "session_engagement_by_period")
GRAINS = ("day", "week", "month")


def _validate(source, analysis_type, grain, breakdown, filters):
    if analysis_type not in MENU:
        raise ValueError(f"unknown analysis_type {analysis_type!r}; valid: {list(MENU)}")
    if grain not in GRAINS:
        raise ValueError(f"unknown grain {grain!r}; valid: {list(GRAINS)}")
    for dim in list(breakdown) + list(filters):
        if dim not in BREAKDOWN_WHITELIST:
            raise ValueError(f"{dim!r} not in breakdown whitelist {list(BREAKDOWN_WHITELIST)}")
        if dim not in source.column_map:
            raise ValueError(f"{dim!r} not mapped in source.column_map")


def _shape_uv_pv(raw, breakdown):
    viz = {
        "chart_type": "line",
        "encoding": {
            "x": "period",
            "y": ["uv", "pv"],
            "series": breakdown[0] if breakdown else None,
        },
    }
    return raw, viz


_BUILDERS = {"uv_pv_by_period": build_uv_pv_sql}
_SHAPERS = {"uv_pv_by_period": _shape_uv_pv}


def run_analysis(config, source, analysis_type, params, run_id, config_version,
                 aggregate_fetcher=None):
    """명명 지표를 파라미터로 요청받아 전수 집계 → shaping → publish_result.

    aggregate_fetcher(config, source, sql) -> DataFrame: 서버 fetch seam(테스트 주입).
    한 run에서 결과를 구분하려면 params["title"]을 다르게 준다(id가 결정적이므로).
    """
    grain = params.get("grain", "day")
    breakdown = params.get("breakdown", [])
    filters = params.get("filters", {})
    _validate(source, analysis_type, grain, breakdown, filters)

    sql = _BUILDERS[analysis_type](source, params["window"], grain, breakdown, filters)
    raw = (aggregate_fetcher or fetch_aggregate)(config, source, sql)

    data, viz = _SHAPERS[analysis_type](raw, breakdown)
    caveats = "전수집계(비샘플)"
    if len(data) == 0:
        caveats += " · no data in window"

    return publish_result(
        config, run_id=run_id, skill="descriptive",
        analysis_type=analysis_type, title=params.get("title", analysis_type),
        data=data, viz=viz, params=params, config_version=config_version,
        caveats=caveats,
    )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_run.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add skills/descriptive/run.py tests/test_descriptive_run.py
git commit -m "feat: add run_analysis with validation and uv_pv publishing"
```

---

## Task 5: `run_analysis` — session_engagement 파생 지표

**Files:**
- Modify: `skills/descriptive/run.py`
- Test: `tests/test_descriptive_run.py` (테스트 추가)

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_descriptive_run.py` 끝에 추가:
```python
def _fake_session(config, source, sql):
    return pd.DataFrame(
        {"period": ["2026-01-05"], "sessions": [8], "uv": [4], "total_duration": [200.0]}
    )


def test_run_session_engagement_derives_per_user(config):
    rid = run_analysis(
        config, _src(), "session_engagement_by_period",
        params={"window": ["2026-01-05", "2026-01-05"], "grain": "day"},
        run_id="r1", config_version="cfg1", aggregate_fetcher=_fake_session,
    )
    df, env = read_result(config, rid)
    assert "uv" not in df.columns                          # uv는 중간값, 최종 출력서 제거
    row = df.iloc[0]
    assert row["sessions_per_user"] == 2.0                 # 8 / 4
    assert row["duration_per_user"] == 50.0                # 200 / 4
    assert row["avg_duration_per_session"] == 25.0         # 200 / 8


def test_run_session_engagement_handles_zero_uv(config):
    def fake(config, source, sql):
        return pd.DataFrame(
            {"period": ["2026-01-05"], "sessions": [0], "uv": [0], "total_duration": [0.0]}
        )

    rid = run_analysis(
        config, _src(), "session_engagement_by_period",
        params={"window": ["2026-01-05", "2026-01-05"]},
        run_id="r1", config_version="cfg1", aggregate_fetcher=fake,
    )
    df, _ = read_result(config, rid)
    assert pd.isna(df.iloc[0]["sessions_per_user"])        # 0으로 나누기 → NA
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_run.py -v`
Expected: FAIL — `KeyError: 'session_engagement_by_period'` (빌더/셰이퍼 미등록)

- [ ] **Step 3: 최소 구현**

`skills/descriptive/run.py` 수정:

import에 `build_session_engagement_sql` 추가:
```python
from skills.descriptive.sql import (
    BREAKDOWN_WHITELIST,
    build_session_engagement_sql,
    build_uv_pv_sql,
)
```

`_shape_uv_pv` 아래에 shaper 추가:
```python
def _shape_session_engagement(raw, breakdown):
    df = raw.copy()
    sessions, uv, dur = df["sessions"], df["uv"], df["total_duration"]
    df["avg_duration_per_session"] = (dur / sessions).where(sessions > 0)
    df["sessions_per_user"] = (sessions / uv).where(uv > 0)
    df["duration_per_user"] = (dur / uv).where(uv > 0)
    df = df.drop(columns=["uv"])
    viz = {
        "chart_type": "line",
        "encoding": {
            "x": "period",
            "y": ["sessions", "sessions_per_user"],
            "series": breakdown[0] if breakdown else None,
        },
    }
    return df, viz
```

`_BUILDERS`/`_SHAPERS` 딕셔너리에 항목 추가:
```python
_BUILDERS = {
    "uv_pv_by_period": build_uv_pv_sql,
    "session_engagement_by_period": build_session_engagement_sql,
}
_SHAPERS = {
    "uv_pv_by_period": _shape_uv_pv,
    "session_engagement_by_period": _shape_session_engagement,
}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_run.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add skills/descriptive/run.py tests/test_descriptive_run.py
git commit -m "feat: add session_engagement analysis with per-user derived metrics"
```

---

## Task 6: 스킬 디스크립터 등록

**Files:**
- Create: `skills/descriptive/descriptor.py`
- Test: `tests/test_descriptive_descriptor.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_descriptive_descriptor.py`:
```python
from data_layer.skills_registry import load_skills_registry
from skills.descriptive.descriptor import register


def test_register_puts_descriptor_in_registry(config):
    register(config)
    reg = load_skills_registry(config)
    match = [s for s in reg if s["name"] == "descriptive"]
    assert len(match) == 1
    assert "uv_pv_by_period" in match[0]["expected_params"]["analysis_type"]
    assert "session_engagement_by_period" in match[0]["expected_params"]["analysis_type"]


def test_register_is_idempotent(config):
    register(config)
    register(config)
    reg = load_skills_registry(config)
    assert sum(1 for s in reg if s["name"] == "descriptive") == 1
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_descriptor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills.descriptive.descriptor'`

- [ ] **Step 3: 최소 구현**

`skills/descriptive/descriptor.py`:
```python
from __future__ import annotations

from data_layer.skills_registry import register_skill

DESCRIPTOR = {
    "name": "descriptive",
    "description": "on-demand 절대(전수) 기술통계: 기간별 UV/PV·세션 engagement",
    "invocation": "run_analysis(config, source, analysis_type, params, run_id, config_version)",
    "expected_params": {
        "analysis_type": ["uv_pv_by_period", "session_engagement_by_period"],
        "window": "[start, end]",
        "grain": ["day", "week", "month"],
        "breakdown": ["app_version", "os", "service_code"],
        "filters": "{column: value}",
    },
}


def register(config) -> None:
    """디스크립티브 스킬 디스크립터를 레지스트리에 upsert (③ 카탈로그용)."""
    register_skill(config, DESCRIPTOR)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_descriptive_descriptor.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 전체 스위트 회귀 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 모두 통과 (기존 64 + 신규 15 = 79 passed, 3 skipped)

- [ ] **Step 6: 커밋**

```bash
git add skills/descriptive/descriptor.py tests/test_descriptive_descriptor.py
git commit -m "feat: register descriptive skill descriptor for platform catalog"
```

---

## Task 7: 실 Trino 통합 스모크 (선택, creds 없으면 skip)

**Files:**
- Create: `tests/integration/test_descriptive_live.py`

- [ ] **Step 1: 통합 테스트 작성**

`tests/integration/test_descriptive_live.py`:
```python
import os
from pathlib import Path

import pytest

from data_layer.config import Config
from data_layer.config_artifacts import events_source_from_json
from data_layer.results import read_result
from skills.descriptive.run import run_analysis

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_creds():
    if not (os.environ.get("TIARA_ID") and os.environ.get("TIARA_PW")):
        pytest.skip("TIARA_ID/TIARA_PW not set")


def test_uv_pv_live_smoke(tmp_path):
    src = events_source_from_json(Path("examples/config/sources.json"), "events")
    config = Config(root=tmp_path / "cache")
    config.ensure_dirs()
    rid = run_analysis(
        config, src, "uv_pv_by_period",
        params={"window": ["2026-01-05", "2026-01-05"], "grain": "day",
                "breakdown": ["app_version"]},
        run_id="live", config_version="live",
    )
    df, env = read_result(config, rid)
    assert {"period", "app_version", "uv", "pv"}.issubset(df.columns)
    assert "전수집계(비샘플)" in env["caveats"]
```

- [ ] **Step 2: 로컬(creds 없음)에서 skip 확인**

Run: `.venv/bin/python -m pytest tests/integration/test_descriptive_live.py -v`
Expected: SKIPPED (TIARA_ID/TIARA_PW not set)

- [ ] **Step 3: 커밋**

```bash
git add tests/integration/test_descriptive_live.py
git commit -m "test: add descriptive uv_pv live Trino smoke (skipped without creds)"
```

---

## Self-Review

**1. Spec coverage:**
- 메뉴 `uv_pv_by_period`/`session_engagement_by_period` → Task 2/3(SQL), 4/5(발행) ✅
- 유저당 세션·체류 파생 → Task 5 ✅
- 세션 = `(app_user_id, isuid)` → Task 3 session_key ✅
- 서버측 전수 집계 + 캐시 프리미티브 → Task 1 ✅
- breakdown 화이트리스트 `{app_version, os, service_code}`, period 항상 포함 → Task 2/4 ✅
- 검증 에러(미지 타입/grain/breakdown) → Task 4 ✅
- UV 비가산성 가드 → Task 3 ✅
- caveats "전수집계(비샘플)" + 빈 결과 처리 → Task 4 ✅
- `register_skill` 카탈로그 → Task 6 ✅
- 통합 스모크 → Task 7 ✅
- 컴포넌트별·분포·gap세션 = 범위 밖(플랜에 없음, 의도적) ✅

**2. Placeholder scan:** 모든 step에 실제 코드/명령/기대출력 포함. "TBD"/"적절히 처리" 없음. ✅

**3. Type consistency:** `fetch_aggregate(config, source, sql, refresh, query_fn)` — Task 1 정의, Task 4/5에서 `aggregate_fetcher(config, source, sql)` 시그니처로 주입(일치). `build_*_sql(source, window, grain, breakdown, filters)` — Task 2/3 정의, Task 4/5 `_BUILDERS`에서 동일 시그니처 호출. raw 컬럼명(`sessions`,`uv`,`total_duration`) — Task 5 fake와 shaper 일치. `publish_result` 인자 — [data_layer/results.py](../../../data_layer/results.py) 실제 시그니처와 일치. ✅

---

## Execution Handoff

계획을 `docs/superpowers/plans/2026-07-23-descriptive-analytics.md`에 저장했습니다. 실행 방식 두 가지:

1. **Subagent-Driven (권장)** — 태스크마다 새 subagent 디스패치, 태스크 사이 리뷰, 빠른 반복.
2. **Inline Execution** — 이 세션에서 executing-plans로 배치 실행 + 체크포인트 리뷰.

어느 쪽으로 할까요?

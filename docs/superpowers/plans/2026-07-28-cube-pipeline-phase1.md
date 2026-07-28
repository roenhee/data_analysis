# 큐브 파이프라인 1단계 (원천 이전 + 재료 파이프라인) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 비식별 테이블 `all_tiara_n` + 성·연령 조인을 원천으로, 코어 7축 세그먼트를 가진 `session`·`transition`·`quality` 큐브를 로컬 parquet로 빌드하는 파이프라인을 만든다.

**Architecture:** Trino에서 CTE 단일 SELECT로 전수 집계(서버 테이블 생성 없음) → 로컬 parquet 캐시. 빌드는 2단계다. 1단계에서 state 사전(화면·클릭레이어·앱버전 상위 목록)을 기간 전체 기준으로 확정하고, 2단계에서 그 사전을 고정한 채 날짜별로 큐브를 빌드한다. 세션은 첫 이벤트 날짜에 귀속하므로 날짜 `D` 빌드는 `date_id IN (D, D+1)` 을 읽는다. 축 정의·프루닝 검증·컷 로직은 모두 DB 없이 테스트 가능한 순수 함수로 분리한다.

**Tech Stack:** Python 3.14, trino-python-client, pandas, duckdb, pytest

**Spec:** `docs/superpowers/specs/2026-07-28-segmented-analytics-design.md`

**Baseline:** 시작 시점 `pytest -q` → `87 passed, 4 skipped`. 매 태스크 후 이 수치가 유지되거나 늘어야 한다(삭제 태스크에서 줄어드는 것은 계획에 명시된 만큼만).

---

## File Structure

**삭제**

| 파일 | 이유 |
|---|---|
| `data_layer/trino_fetcher.py` | 표본 경로 전용(임시테이블 생성). 전수 확정으로 불필요 |
| `data_layer/cleanup.py` | 임시테이블 청소용. 테이블을 안 만들므로 불필요 |
| `tests/test_trino_fetcher.py` | 위 삭제에 따라 |
| `tests/test_cleanup.py` | 위 삭제에 따라 |
| `tests/integration/test_fetch_live.py` | 표본 fetch 라이브 테스트 |

**수정**

| 파일 | 변경 |
|---|---|
| `examples/config/sources.json` | `all_tiara_n` 좌표 + 성연령 소스 추가, `date.day` 오매핑 제거 |
| `data_layer/sql_builder.py` | `build_prepare_sql`·`build_partition_sql` 삭제. `build_action_counts_sql` 은 `analytics/cube/state_sql.py` 로 이전 후 파일 삭제 |
| `data_layer/fetch.py` | `entities` 계산의 `app_user_id` → `uuid` |
| `data_layer/enrich.py` | `join_dim` 기본 key `app_user_id` → `uuid` |
| `tests/conftest.py` | `sample_events` fixture를 `uuid`/`suid` 기준으로 |
| `tests/test_sql_builder.py` | 삭제될 함수 테스트 제거 |
| `tests/test_fetch.py`, `tests/test_enrich.py` | 컬럼명 전환 반영 |

**신규**

| 파일 | 책임 |
|---|---|
| `analytics/__init__.py` | 패키지 마커 |
| `analytics/cube/__init__.py` | 패키지 마커 |
| `analytics/cube/axes.py` | 코어 7축의 이름과 Trino 표현식. DB 무의존 순수 함수 |
| `analytics/cube/guard.py` | 파티션 프루닝 강제, `NOT IN` 금지 검증 |
| `analytics/cube/state_dict.py` | state 사전 자료구조·컷 로직·저장/로드 |
| `analytics/cube/state_sql.py` | state 사전 생성용 집계 SQL |
| `analytics/cube/store.py` | 큐브 캐시 키·parquet 경로 규약과 읽기/쓰기 |
| `analytics/cube/sql.py` | `session`·`transition`·`quality` 큐브 집계 SQL |
| `analytics/cube/builder.py` | 2단계 빌드 오케스트레이션, 증분 스킵 |
| `tests/__init__.py` | **필수.** 없으면 pytest가 `tests/analytics/test_axes.py` 의 모듈명을 `analytics.test_axes` 로 유도해 진짜 `analytics` 패키지를 가려버리고 `from analytics.cube... import` 가 `ModuleNotFoundError` 로 실패한다. 빈 파일 |
| `tests/analytics/__init__.py` | 빈 파일 |
| `tests/analytics/test_axes.py` 등 | 위 각 모듈 테스트 |
| `tests/integration/test_cube_live.py` | 라이브 스모크 |

---

### Task 1: sources.json 을 새 좌표로 재작성

**Files:**
- Modify: `examples/config/sources.json`
- Test: `tests/test_config_artifacts.py`

- [ ] **Step 1: 기존 테스트 확인**

Run: `.venv/bin/python -m pytest tests/test_config_artifacts.py -v`
Expected: PASS (현재 `axz_tiara` 스키마를 기대)

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_config_artifacts.py` 끝에 추가:

```python
def test_events_source_points_at_deidentified_table():
    srcs = load_sources(Path("examples/config/sources.json"))
    src = srcs["events"]
    assert src.table == "all_tiara_n"
    assert src.catalog == "bigdata_omega_common_iceberg"
    assert src.schema == "axz_tiara"
    # 비식별 테이블의 식별자
    assert src.column_map["uuid"] == "user.uuid"
    assert src.column_map["suid"] == "user.suid"
    # 파티션 컬럼이 매핑에 있어야 프루닝 SQL을 만들 수 있다
    assert src.column_map["date_id"] == "date_id"
    assert src.column_map["service_code"] == "c_service_code"
    # date.day 는 '요일'이므로 날짜 축으로 쓰면 안 된다
    assert "day" not in src.column_map


def test_demography_source_is_declared():
    srcs = load_sources(Path("examples/config/sources.json"))
    dem = srcs["demography"]
    assert dem.catalog == "hadoop_doopey"
    assert dem.schema == "target_subcom"
    assert dem.table == "tb_axz_demography_uuid_v2"
    assert dem.column_map["uuid"] == "uuid"
    assert dem.column_map["gender"] == "gender"
    assert dem.column_map["age_band"] == "service_age_band"
```

`tests/test_config_artifacts.py` 상단에 `from pathlib import Path` 와 `from data_layer.sources import load_sources` 가 없으면 추가한다.

- [ ] **Step 3: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_config_artifacts.py -v`
Expected: FAIL — `assert 'all_tiara_i' == 'all_tiara_n'`

- [ ] **Step 4: sources.json 재작성**

`examples/config/sources.json` 전체를 아래로 교체:

```json
[
  {
    "id": "events",
    "kind": "trino",
    "host": "hadoop-rabbit-trino.onkakao.net",
    "port": 8443,
    "catalog": "bigdata_omega_common_iceberg",
    "schema": "axz_tiara",
    "table": "all_tiara_n",
    "auth_ref": "TIARA",
    "column_map": {
      "uuid": "user.uuid",
      "suid": "user.suid",
      "access_time": "try_cast(common.access_time AS timestamp)",
      "date_id": "date_id",
      "service_code": "c_service_code",
      "service_type": "common.service_type",
      "action_type": "action.type",
      "action_name": "action.name",
      "action_kind": "action.kind",
      "daypart": "date.daypart",
      "os": "env.os",
      "app_version": "env.app_version",
      "layer1": "click.layer1",
      "layer2": "click.layer2",
      "page": "common.page",
      "usage_duration": "try(cast(usage.duration as double))",
      "is_invalid": "tag.is_invalid"
    },
    "filters": [
      "NULLIF(TRIM(user.uuid), '') IS NOT NULL",
      "NULLIF(TRIM(user.suid), '') IS NOT NULL",
      "try_cast(common.access_time AS timestamp) IS NOT NULL",
      "coalesce(tag.is_invalid, '0') <> '1'"
    ]
  },
  {
    "id": "demography",
    "kind": "trino",
    "host": "hadoop-rabbit-trino.onkakao.net",
    "port": 8443,
    "catalog": "hadoop_doopey",
    "schema": "target_subcom",
    "table": "tb_axz_demography_uuid_v2",
    "auth_ref": "TIARA",
    "column_map": {
      "uuid": "uuid",
      "gender": "gender",
      "age_band": "service_age_band"
    },
    "filters": []
  }
]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_config_artifacts.py -v`
Expected: PASS

- [ ] **Step 6: 전체 스위트 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: `all_tiara_i` 를 기대하는 `tests/test_sql_builder.py` 가 깨질 수 있다. 깨지면 그대로 두고 Task 2에서 처리한다. 그 외 실패는 없어야 한다.

- [ ] **Step 7: 커밋**

```bash
git add examples/config/sources.json tests/test_config_artifacts.py
git commit -m "feat: point sources at all_tiara_n and declare demography source"
```

---

### Task 2: 표본 경로 삭제

**Files:**
- Delete: `data_layer/trino_fetcher.py`, `data_layer/cleanup.py`, `data_layer/sql_builder.py`
- Delete: `tests/test_trino_fetcher.py`, `tests/test_cleanup.py`, `tests/test_sql_builder.py`, `tests/integration/test_fetch_live.py`
- Modify: `data_layer/__init__.py`

- [ ] **Step 1: `__init__.py` 에서 무엇을 내보내는지 확인**

Run: `grep -n "trino_fetcher\|cleanup\|sql_builder" data_layer/__init__.py`
Expected: 해당 이름들의 import 라인 출력 (없으면 다음 스텝에서 건드릴 것 없음)

- [ ] **Step 2: 다른 곳에서 쓰는지 확인**

Run: `grep -rn "trino_fetcher\|drop_temp_tables\|build_prepare_sql\|build_partition_sql\|build_action_counts_sql" --include=*.py . | grep -v "^./.venv" | grep -v "^./tests/test_trino_fetcher\|^./tests/test_cleanup\|^./tests/test_sql_builder"`
Expected: `data_layer/__init__.py` 와 `tests/integration/test_fetch_live.py` 정도만. 다른 프로덕션 코드에서 쓰이면 그 사용처를 먼저 정리한다.

- [ ] **Step 3: 삭제 실행**

```bash
git rm data_layer/trino_fetcher.py data_layer/cleanup.py data_layer/sql_builder.py
git rm tests/test_trino_fetcher.py tests/test_cleanup.py tests/test_sql_builder.py
git rm tests/integration/test_fetch_live.py
```

- [ ] **Step 4: `data_layer/__init__.py` 에서 참조 제거**

Step 1에서 찾은 `trino_fetcher` / `cleanup` / `sql_builder` 관련 import 와 `__all__` 항목을 삭제한다. 남는 import 는 건드리지 않는다.

- [ ] **Step 5: 스위트 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. 테스트 수는 87 − (삭제한 파일들의 테스트 수) 로 줄어든다. 실패는 0이어야 한다.

- [ ] **Step 6: 임포트 정합성 확인**

Run: `.venv/bin/python -c "import data_layer; print('ok')"`
Expected: `ok`

- [ ] **Step 7: 커밋**

```bash
git add -A
git commit -m "refactor: drop sampling path (temp tables no longer needed)

Full-population cube aggregation runs as a single CTE SELECT, so the
server-side temp table lifecycle and its cleanup sweep have no callers.
Removing them also makes the data-hub rule -- do not leave data under the
group account -- structurally impossible to violate."
```

---

### Task 3: 표본 시대 잔여 모듈 정리

**계획 수정 이력:** 원래 이 태스크는 `fetch.py`·`enrich.py` 의 기본 키 이름을
`app_user_id` → `uuid` 로 바꾸는 작업이었다. Task 2의 코드 품질 리뷰에서 이 모듈들이
프로덕션 호출자가 없는 표본 시대 코드임이 드러났다. 죽은 코드의 컬럼명을 다듬으면
살아있는 것처럼 보이게 만들 뿐이므로, 이름을 바꾸는 대신 삭제한다.

**삭제 근거 (모듈별)**

| 모듈 | 근거 |
|---|---|
| `convergence.py` | `check_convergence(analysis_fn, sizes, tol)` 는 표본 크기를 키우며 지표 안정성을 확인한다. 전수 집계로 확정했으므로 키울 표본 크기가 없다 |
| `fetch.py` | `get_events` 는 원본 이벤트를 날짜별로 로컬 parquet에 당긴다. 큐브 설계는 집계 결과만 내리며 원본을 로컬에 두지 않는다 |
| `enrich.py` | `join_dim` 은 로컬 DuckDB에서 이벤트와 차원을 조인한다. 성·연령은 서버측 SQL `JOIN` 으로 붙는다 |

`data_layer/query.py` 는 **삭제하지 않는다.** 표본 코드가 아니라 범용 로컬 DuckDB 실행+캐시
프리미티브이고, 대체물(`analytics/cube/store.read_cube`)이 아직 없으므로 폐기 판단은 예측에
불과하다. Phase 2에서 `metrics/` 가 큐브를 실제로 읽는 방식이 정해진 뒤 근거를 갖고 결정한다.

**Files:**
- Delete: `data_layer/convergence.py`, `data_layer/fetch.py`, `data_layer/enrich.py`
- Delete: `tests/test_convergence.py`, `tests/test_fetch.py`, `tests/test_enrich.py`
- Modify: `data_layer/__init__.py`, `tests/test_util.py`, `tests/conftest.py`

- [ ] **Step 1: 호출자가 없음을 재확인**

Run:
```bash
grep -rn "data_layer.convergence|data_layer.fetch |data_layer.enrich|check_convergence|get_events|read_partitions|missing_start_days|join_dim" --include='*.py' -E . | grep -v "\.venv"
```
Expected: `data_layer/__init__.py` 와 삭제 대상 테스트 파일들만. `data_layer/fetch_aggregate.py`
는 이름이 비슷하지만 **다른 모듈이고 유지 대상**이므로 결과에 섞여 나오면 무시한다.

프로덕션 파일에서 참조가 나오면 **STOP 하고 NEEDS_CONTEXT 로 보고**한다.

- [ ] **Step 2: 삭제**

```bash
git rm data_layer/convergence.py data_layer/fetch.py data_layer/enrich.py
git rm tests/test_convergence.py tests/test_fetch.py tests/test_enrich.py
```

- [ ] **Step 3: `data_layer/__init__.py` 정리**

`convergence`, `fetch`, `enrich` 관련 import 와 `__all__` 항목(`check_convergence`,
`get_events`, `join_dim`)을 삭제한다. `fetch_aggregate` 는 **남긴다**. 다른 import 는 건드리지 않는다.

- [ ] **Step 4: `tests/test_util.py` 정리**

export 검증 튜플에서 `"get_events"` 를 제거한다. 다른 부분은 건드리지 않는다.

- [ ] **Step 5: `tests/conftest.py` 의 미사용 fixture 삭제**

`sample_events` fixture 는 `test_fetch.py`·`test_enrich.py` 만 사용했으므로 이제 아무도 쓰지
않는다. fixture 전체와 그 때문에만 필요한 `import pandas as pd` 를 삭제한다.
`config` fixture 와 그 import 는 남긴다.

삭제 전에 확인:
```bash
grep -rn "sample_events" --include='*.py' . | grep -v "\.venv"
```
Expected: `tests/conftest.py` 만 (다른 파일이 나오면 STOP 하고 보고).

- [ ] **Step 6: 스위트 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: **65 passed, 3 skipped**, 실패 0.

도출: 현재 75 passed / 3 skipped. 삭제되는 통과 테스트는 `test_convergence` 2 +
`test_fetch` 6 + `test_enrich` 2 = 10개. 75 − 10 = 65.
다른 숫자가 나오면 무관한 테스트를 고치지 말고 조사해 보고한다.

- [ ] **Step 7: 임포트 확인**

Run: `.venv/bin/python -c "import data_layer; print('ok')"`
Expected: `ok`

- [ ] **Step 8: 잔여 참조 확인**

Run:
```bash
grep -rn "check_convergence|get_events|read_partitions|missing_start_days|join_dim|data_layer.enrich|data_layer.convergence" --include='*.py' -E . | grep -v "\.venv"
```
Expected: 출력 없음.

`app_user_id`/`isuid` 잔여도 확인:
```bash
grep -rn "app_user_id|isuid" --include='*.py' -E . | grep -v "\.venv"
```
Expected: `skills/descriptive/` 와 `tests/test_descriptive_*.py`, `tests/test_manifest.py`,
`tests/test_fetch_aggregate.py` 만 남는다. 이들은 **Phase 2 흡수 대상이므로 이 태스크에서
건드리지 않는다.** 목록을 보고에 그대로 적는다.

- [ ] **Step 9: 커밋**

`.DS_Store` 가 스테이징되지 않도록 `git add -A` 를 쓰지 말고 파일을 명시한다.

```bash
git add data_layer/__init__.py tests/test_util.py tests/conftest.py
git commit -F - <<'MSG'
refactor: remove sampling-era modules with no callers

convergence.py grew a sample until metrics stabilised; with full-population
aggregation there is no sample size to grow. fetch.py pulled raw events into
local parquet and enrich.py joined dimensions locally; the cube design lands
only aggregates and joins demography server-side in SQL. None of the three had
a production caller -- only their own tests and package exports.

Renaming their key columns to uuid, as originally planned, would have polished
dead code into looking alive.

query.py stays for now: it is a general local-DuckDB execute-and-cache
primitive rather than sampling code, and its replacement does not exist yet.
MSG
```

---

### Task 4: 코어 7축 정의 (`analytics/cube/axes.py`)

**Files:**
- Create: `analytics/__init__.py`, `analytics/cube/__init__.py`, `analytics/cube/axes.py`
- Create: `tests/analytics/__init__.py`, `tests/analytics/test_axes.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_axes.py`:

```python
from analytics.cube.axes import (
    CORE_AXIS_NAMES,
    age_band_expr,
    app_version_expr,
    core_axis_selects,
    os_expr,
)


def test_core_axis_names_are_the_seven_from_the_spec():
    assert CORE_AXIS_NAMES == (
        "period",
        "service_type",
        "os",
        "gender",
        "age_band",
        "daypart",
        "app_version",
    )


def test_os_expr_buckets_known_families_and_folds_the_rest():
    sql = os_expr()
    for family in ("android", "ios", "windows", "macos"):
        assert f"'{family}'" in sql
    assert "'other'" in sql
    # 실측된 os 값은 소문자다
    assert "lower(" in sql


def test_app_version_expr_keeps_listed_versions_and_folds_others():
    sql = app_version_expr(["9.5.1", "9.5.0"])
    assert "'9.5.1'" in sql
    assert "'9.5.0'" in sql
    assert "'other'" in sql


def test_app_version_expr_escapes_single_quotes():
    sql = app_version_expr(["9.5'1"])
    assert "9.5''1" in sql


def test_app_version_expr_with_no_versions_is_all_other():
    sql = app_version_expr([])
    assert sql.strip() == "'other'"


def test_core_axis_selects_emits_one_alias_per_axis_in_order():
    selects = core_axis_selects(["9.5.1"])
    assert len(selects) == len(CORE_AXIS_NAMES)
    for sel, name in zip(selects, CORE_AXIS_NAMES):
        assert sel.endswith(f" AS {name}")


def test_unmatched_demography_becomes_unknown_not_null():
    selects = core_axis_selects(["9.5.1"])
    gender = next(s for s in selects if s.endswith(" AS gender"))
    age = next(s for s in selects if s.endswith(" AS age_band"))
    assert "'unknown'" in gender
    assert "'unknown'" in age


def test_age_band_folds_the_source_unknown_sentinel_into_unknown():
    # service_age_band 의 0 은 원천의 '연령 미상' 센티널이므로 NULL과 같은 버킷이어야 한다.
    # 나누면 축이 8개가 아니라 9개 값이 되고 unknown 필터가 과소집계한다.
    sql = age_band_expr()
    assert "= 0" in sql
    assert "'unknown'" in sql


def _by_axis(versions, **kw):
    return {s.rsplit(" AS ", 1)[1]: s for s in core_axis_selects(versions, **kw)}


def test_each_axis_select_carries_its_own_source_column():
    # 축 이름과 표현식의 짝이 어긋나도 통과하는 테스트를 막는다.
    sel = _by_axis(["9.5.1"])
    assert sel["period"].startswith("date_id")
    assert "common.service_type" in sel["service_type"]
    assert "env.os" in sel["os"]
    assert "d.gender" in sel["gender"] and "service_age_band" not in sel["gender"]
    assert "service_age_band" in sel["age_band"] and "d.gender" not in sel["age_band"]
    assert "date.daypart" in sel["daypart"]
    assert "env.app_version" in sel["app_version"]


def test_dim_alias_is_plumbed_into_both_demography_axes():
    sel = _by_axis(["9.5.1"], dim_alias="dem")
    assert "dem.gender" in sel["gender"]
    assert "dem.service_age_band" in sel["age_band"]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_axes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics'`

- [ ] **Step 3: 구현**

`analytics/__init__.py` 와 `analytics/cube/__init__.py` 는 빈 파일로 만든다.

`analytics/cube/axes.py`:

```python
"""코어 7축의 이름과 Trino 표현식. DB에 접근하지 않는 순수 함수."""
from __future__ import annotations

CORE_AXIS_NAMES = (
    "period",
    "service_type",
    "os",
    "gender",
    "age_band",
    "daypart",
    "app_version",
)

OS_FAMILIES = ("android", "ios", "windows", "macos")


def _lit(value) -> str:
    """SQL 문자열 리터럴. 단일 인용부호를 이스케이프한다."""
    return "'" + str(value).replace("'", "''") + "'"


def period_expr() -> str:
    return "date_id"


def service_type_expr() -> str:
    return "coalesce(nullif(trim(common.service_type), ''), 'unknown')"


def os_expr() -> str:
    whens = " ".join(
        f"WHEN {_lit(f)} THEN {_lit(f)}" for f in OS_FAMILIES
    )
    return f"CASE lower(coalesce(env.os, '')) {whens} ELSE 'other' END"


def daypart_expr() -> str:
    return "coalesce(nullif(trim(date.daypart), ''), 'unknown')"


def gender_expr(dim_alias: str = "d") -> str:
    return f"coalesce(nullif(trim({dim_alias}.gender), ''), 'unknown')"


def age_band_expr(dim_alias: str = "d") -> str:
    """`service_age_band` 의 `0` 은 원천이 쓰는 '연령 미상' 센티널이다.

    매칭 실패(NULL)와 **같은 `'unknown'` 한 버킷으로 접는다.** 둘을 나누면 스펙이 정의한
    8개 값이 9개가 되고, `age_band='unknown'` 으로 필터하는 소비자가 미상 유저의
    대부분(전체 성연령 테이블의 64%)을 조용히 놓친다. 매칭 여부 자체의 구분은 축이 아니라
    커버리지·`quality` 큐브에서 다룬다.
    """
    col = f"{dim_alias}.service_age_band"
    return (
        f"CASE WHEN {col} IS NULL OR {col} = 0 THEN 'unknown' "
        f"ELSE cast({col} AS varchar) END"
    )


def app_version_expr(versions: list[str]) -> str:
    if not versions:
        return "'other'"
    listed = ", ".join(_lit(v) for v in versions)
    return (
        f"CASE WHEN env.app_version IN ({listed}) "
        f"THEN env.app_version ELSE 'other' END"
    )


def core_axis_selects(versions: list[str], dim_alias: str = "d") -> list[str]:
    """`<expr> AS <axis>` 형태의 SELECT 절 목록. CORE_AXIS_NAMES 순서와 같다."""
    exprs = (
        period_expr(),
        service_type_expr(),
        os_expr(),
        gender_expr(dim_alias),
        age_band_expr(dim_alias),
        daypart_expr(),
        app_version_expr(versions),
    )
    return [f"{e} AS {name}" for e, name in zip(exprs, CORE_AXIS_NAMES)]
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_axes.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics tests/analytics
git commit -m "feat: define the seven core cube axes as pure SQL expressions"
```

---

### Task 5: 프루닝·NULL 규약 강제 (`analytics/cube/guard.py`)

**Files:**
- Create: `analytics/cube/guard.py`
- Create: `tests/analytics/test_guard.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_guard.py`:

```python
import pytest

from analytics.cube.guard import GuardError, assert_safe_sql

PRUNED = """
SELECT count(*) FROM t
WHERE date_id IN ('2026-07-27')
  AND c_service_code IN ('top')
"""


def test_pruned_sql_passes():
    assert_safe_sql(PRUNED) is None


def test_missing_date_id_is_rejected():
    sql = "SELECT count(*) FROM t WHERE c_service_code IN ('top')"
    with pytest.raises(GuardError, match="date_id"):
        assert_safe_sql(sql)


def test_missing_service_code_is_rejected():
    sql = "SELECT count(*) FROM t WHERE date_id IN ('2026-07-27')"
    with pytest.raises(GuardError, match="c_service_code"):
        assert_safe_sql(sql)


def test_not_in_is_rejected_because_null_poisons_it():
    sql = PRUNED + " AND action.name NOT IN ('a')"
    with pytest.raises(GuardError, match="NOT IN"):
        assert_safe_sql(sql)


def test_not_in_detection_is_case_insensitive_and_whitespace_tolerant():
    sql = PRUNED + " AND action.name not   in ('a')"
    with pytest.raises(GuardError, match="NOT IN"):
        assert_safe_sql(sql)


def test_not_null_is_not_mistaken_for_not_in():
    sql = PRUNED + " AND action.name IS NOT NULL"
    assert assert_safe_sql(sql) is None


def test_pruning_column_only_in_the_select_list_is_rejected():
    # 가장 현실적인 실수: SELECT 에는 넣고 WHERE 에는 빼먹는다.
    sql = "SELECT date_id, count(*) FROM t WHERE c_service_code IN ('top')"
    with pytest.raises(GuardError, match="date_id"):
        assert_safe_sql(sql)


def test_pruning_column_only_in_a_comment_is_rejected():
    sql = "-- date_id filter TODO\nSELECT count(*) FROM t WHERE c_service_code IN ('top')"
    with pytest.raises(GuardError, match="date_id"):
        assert_safe_sql(sql)


def test_longer_identifier_containing_the_column_is_not_accepted():
    sql = "SELECT 1 FROM t WHERE my_date_id_backup = '1' AND c_service_code IN ('top')"
    with pytest.raises(GuardError, match="date_id"):
        assert_safe_sql(sql)


def test_sql_without_a_where_clause_is_rejected():
    with pytest.raises(GuardError):
        assert_safe_sql("SELECT count(*) FROM t")


def test_column_matching_is_case_insensitive():
    sql = "SELECT 1 FROM t WHERE DATE_ID IN ('x') AND C_SERVICE_CODE IN ('y')"
    assert assert_safe_sql(sql) is None


def test_ne_all_is_banned_like_not_in():
    sql = PRUNED + " AND action.name <> ALL (ARRAY['a'])"
    with pytest.raises(GuardError, match="NOT IN"):
        assert_safe_sql(sql)


def test_known_limitation_subquery_only_constraint_still_passes():
    """파서 없이는 못 잡는 알려진 한계를 고정한다.

    바깥 스캔은 안 잘리지만 통과한다. 이 테스트가 깨지면 가드가 더 엄격해진 것이므로
    한계 문서를 함께 갱신한다.
    """
    sql = (
        "SELECT 1 FROM t WHERE date_id IN ('x') "
        "AND x IN (SELECT c_service_code FROM other)"
    )
    assert assert_safe_sql(sql) is None
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_guard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.cube.guard'`

- [ ] **Step 3: 구현**

`analytics/cube/guard.py`:

```python
"""큐브 SQL의 안전 규약 검증.

- 파티션 프루닝(`date_id`, `c_service_code`)이 없는 쿼리는 5,249억 행 테이블을
  풀스캔하므로 실행 전에 막는다.
- `NOT IN` 은 서브쿼리에 NULL이 하나라도 있으면 조용히 0행을 반환한다. 에러도 나지
  않고 그냥 틀린 답이 나오므로 금지하고 `NOT EXISTS` / `LEFT JOIN` 을 쓴다.
"""
from __future__ import annotations

import re

REQUIRED_PRUNING_COLUMNS = ("date_id", "c_service_code")

# NOT IN 과 <> ALL 은 Trino에서 같은 의미이고 같은 NULL 오염을 갖는다.
_NULL_POISONED = (
    re.compile(r"\bnot\s+in\b", re.IGNORECASE),
    re.compile(r"<>\s*all\b", re.IGNORECASE),
)
_WHERE = re.compile(r"\bwhere\b", re.IGNORECASE)
_LINE_COMMENT = re.compile(r"--[^\n]*")


class GuardError(ValueError):
    """SQL 안전 규약 위반."""


def _filter_text(sql: str) -> str:
    """주석을 지우고 첫 `WHERE` 이후 텍스트만 남긴다.

    프루닝 컬럼이 SELECT 목록이나 주석에만 등장하는 것을 '프루닝됨'으로 오인하지 않기
    위한 것이다. `WHERE` 가 아예 없으면 빈 문자열을 반환해 반드시 거부되게 한다.
    """
    stripped = _LINE_COMMENT.sub(" ", sql)
    m = _WHERE.search(stripped)
    return stripped[m.end():] if m else ""


def assert_safe_sql(sql: str) -> None:
    """큐브 SQL의 안전 규약을 검사하고 위반 시 `GuardError` 를 던진다.

    **한계**: 프루닝 컬럼이 `WHERE` 이후에 독립 토큰으로 등장하는지까지만 본다.
    서브쿼리 안에서만 제약되어 바깥 스캔은 안 잘리는 경우는 잡지 못한다. 그걸 잡으려면
    SQL 파서가 필요하고, 이 가드의 호출자는 우리 자신의 SQL 빌더(Task 12)이므로
    파서까지는 가지 않는다. 이 함수는 "프루닝이 유효하다"가 아니라
    "프루닝 컬럼이 필터 위치에 있다"를 보증한다.
    """
    filters = _filter_text(sql).lower()
    for column in REQUIRED_PRUNING_COLUMNS:
        # 단어 경계: my_date_id_backup 같은 다른 식별자의 부분문자열을 인정하지 않는다.
        if not re.search(rf"\b{re.escape(column)}\b", filters):
            raise GuardError(
                f"partition pruning column {column!r} is absent from the WHERE "
                "clause; add it as a filter or the query will full-scan "
                "all_tiara_n (524 billion rows)"
            )
    for pattern in _NULL_POISONED:
        if pattern.search(sql):
            raise GuardError(
                "NOT IN / <> ALL are banned (a single NULL on the right-hand "
                "side silently yields zero rows); use NOT EXISTS or a LEFT JOIN"
            )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_guard.py -q`
Expected: PASS (13 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/cube/guard.py tests/analytics/test_guard.py
git commit -m "feat: enforce partition pruning and ban NOT IN in cube SQL"
```

---

### Task 6: state 사전 컷 로직 (`analytics/cube/state_dict.py`)

**Files:**
- Create: `analytics/cube/state_dict.py`
- Create: `tests/analytics/test_state_dict.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_state_dict.py`:

```python
import pandas as pd

from analytics.cube.state_dict import StateDict, apply_cut, load_state_dict, save_state_dict


def _counts(pairs):
    return pd.DataFrame(pairs, columns=["value", "cnt"])


def test_apply_cut_keeps_values_up_to_the_coverage_ratio():
    counts = _counts([("a", 700), ("b", 250), ("c", 50)])
    kept = apply_cut(counts, cut_ratio=0.95, min_count=0)
    assert kept == ["a", "b"]


def test_apply_cut_drops_values_below_min_count_even_inside_the_ratio():
    counts = _counts([("a", 700), ("b", 250), ("c", 50)])
    kept = apply_cut(counts, cut_ratio=0.95, min_count=300)
    assert kept == ["a"]


def test_apply_cut_returns_values_ordered_by_count_desc():
    counts = _counts([("small", 10), ("big", 990)])
    kept = apply_cut(counts, cut_ratio=1.0, min_count=0)
    assert kept == ["big", "small"]


def test_apply_cut_on_empty_input_returns_empty():
    assert apply_cut(_counts([]), cut_ratio=0.95, min_count=0) == []


def test_version_changes_when_any_kept_list_changes():
    a = StateDict(screens=["top/홈탭"], layer1=["home_main"], layer2=[],
                  app_versions=["9.5.1"], cut_ratio=0.95, min_count=10000)
    b = StateDict(screens=["top/홈탭", "top/콘텐츠탭"], layer1=["home_main"], layer2=[],
                  app_versions=["9.5.1"], cut_ratio=0.95, min_count=10000)
    assert a.version() != b.version()


def test_version_changes_when_cut_config_changes():
    a = StateDict(screens=["s"], layer1=[], layer2=[], app_versions=[],
                  cut_ratio=0.95, min_count=10000)
    b = StateDict(screens=["s"], layer1=[], layer2=[], app_versions=[],
                  cut_ratio=0.90, min_count=10000)
    assert a.version() != b.version()


def test_version_is_stable_across_equal_dicts():
    kw = dict(screens=["s"], layer1=["l"], layer2=[], app_versions=["v"],
              cut_ratio=0.95, min_count=10000)
    assert StateDict(**kw).version() == StateDict(**kw).version()


def test_save_then_load_roundtrips(config):
    sd = StateDict(screens=["top/홈탭_진입"], layer1=["home_main"], layer2=["FEED_SLOT_ISSUE"],
                   app_versions=["9.5.1", "9.5.0"], cut_ratio=0.95, min_count=10000)
    path = save_state_dict(config, sd)
    assert path.exists()
    loaded = load_state_dict(config, sd.version())
    assert loaded == sd
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_state_dict.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.cube.state_dict'`

- [ ] **Step 3: 구현**

`analytics/cube/state_dict.py`:

```python
"""state 사전: 큐브 빌드 전에 확정해 고정하는 값 목록.

화면·클릭레이어·앱버전의 채택 목록을 담는다. 날짜별 큐브 빌드는 이 사전을 고정한 채
수행되므로, 나중에 날짜를 추가해도 앞선 날짜의 state 집합이 흔들리지 않는다.
버전 비교 시에는 비교 대상 기간·버전을 합쳐 사전을 한 번만 만든다.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from data_layer.config import Config
from data_layer.util import content_hash

DEFAULT_CUT_RATIO = 0.95
DEFAULT_MIN_COUNT = 10_000


def apply_cut(counts: pd.DataFrame, cut_ratio: float, min_count: int) -> list[str]:
    """건수 내림차순으로 누적 커버리지 `cut_ratio` 까지 채택. `min_count` 미만은 제외.

    `counts` 는 `value`, `cnt` 두 컬럼을 갖는다.
    """
    if counts.empty:
        return []
    ordered = counts.sort_values("cnt", ascending=False, kind="mergesort")
    total = ordered["cnt"].sum()
    if total <= 0:
        return []
    cumulative = ordered["cnt"].cumsum()
    # 컷 경계에 걸친 값은 포함한다(누적이 처음 비율을 넘는 지점까지).
    within = cumulative.shift(fill_value=0) < cut_ratio * total
    kept = ordered[within & (ordered["cnt"] >= min_count)]
    return [str(v) for v in kept["value"].tolist()]


@dataclass(frozen=True)
class StateDict:
    screens: list[str]
    layer1: list[str]
    layer2: list[str]
    app_versions: list[str]
    cut_ratio: float = DEFAULT_CUT_RATIO
    min_count: int = DEFAULT_MIN_COUNT

    def version(self) -> str:
        return "sd_" + content_hash(
            self.screens,
            self.layer1,
            self.layer2,
            self.app_versions,
            self.cut_ratio,
            self.min_count,
        )


def _dir(config: Config) -> Path:
    return config.root / "state_dicts"


def save_state_dict(config: Config, sd: StateDict) -> Path:
    d = _dir(config)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{sd.version()}.json"
    payload = asdict(sd) | {"version": sd.version()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def load_state_dict(config: Config, version: str) -> StateDict:
    path = _dir(config) / f"{version}.json"
    raw = json.loads(path.read_text())
    raw.pop("version", None)
    return StateDict(**raw)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_state_dict.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/cube/state_dict.py tests/analytics/test_state_dict.py
git commit -m "feat: add state dictionary with coverage cut and stable versioning"
```

---

### Task 7: state 사전 생성 SQL (`analytics/cube/state_sql.py`)

**Files:**
- Create: `analytics/cube/state_sql.py`
- Create: `tests/analytics/test_state_sql.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_state_sql.py`:

```python
from analytics.cube.guard import assert_safe_sql
from analytics.cube.state_sql import (
    build_layer1_count_sql,
    build_layer2_count_sql,
    build_screen_count_sql,
    build_version_count_sql,
)

WINDOW = ("2026-07-01", "2026-07-31")
SERVICES = ["top", "media"]
TABLE = "bigdata_omega_common_iceberg.axz_tiara.all_tiara_n"


def test_screen_count_sql_is_pruned_and_safe():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert_safe_sql(sql)


def test_screen_count_sql_selects_value_and_cnt():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "AS value" in sql
    assert "AS cnt" in sql


def test_screen_count_sql_uses_pageview_only():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "action.type = 'Pageview'" in sql


def test_screen_value_is_service_slash_name():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "c_service_code" in sql and "'/'" in sql


def test_window_bounds_are_inclusive_on_date_id():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "date_id BETWEEN '2026-07-01' AND '2026-07-31'" in sql


def test_services_are_quoted_into_an_in_list():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "c_service_code IN ('top', 'media')" in sql


def test_layer1_and_layer2_sql_are_pruned_and_safe():
    for builder in (build_layer1_count_sql, build_layer2_count_sql):
        assert_safe_sql(builder(TABLE, WINDOW, SERVICES))


def test_layer2_value_is_layer1_gt_layer2():
    sql = build_layer2_count_sql(TABLE, WINDOW, SERVICES)
    assert "'>'" in sql


def test_version_count_sql_is_pruned_and_safe():
    assert_safe_sql(build_version_count_sql(TABLE, WINDOW, SERVICES))


def test_service_list_escapes_single_quotes():
    sql = build_screen_count_sql(TABLE, WINDOW, ["o'hara"])
    assert "o''hara" in sql
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_state_sql.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.cube.state_sql'`

- [ ] **Step 3: 구현**

`analytics/cube/state_sql.py`:

```python
"""state 사전 생성용 집계 SQL. 전이를 계산하지 않으므로 가볍다."""
from __future__ import annotations

BASE_FILTERS = (
    "NULLIF(TRIM(user.uuid), '') IS NOT NULL",
    "NULLIF(TRIM(user.suid), '') IS NOT NULL",
    "try_cast(common.access_time AS timestamp) IS NOT NULL",
    "coalesce(tag.is_invalid, '0') <> '1'",
)


def _lit(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _in_list(values) -> str:
    return ", ".join(_lit(v) for v in values)


def _where(window: tuple[str, str], services: list[str], extra: list[str]) -> str:
    start, end = window
    conds = [
        f"date_id BETWEEN {_lit(start)} AND {_lit(end)}",
        f"c_service_code IN ({_in_list(services)})",
        *BASE_FILTERS,
        *extra,
    ]
    return "\n  AND ".join(conds)


def _count_sql(table, window, services, value_expr, extra) -> str:
    return (
        f"SELECT {value_expr} AS value, count(*) AS cnt\n"
        f"FROM {table}\n"
        f"WHERE {_where(window, services, extra)}\n"
        "GROUP BY 1\n"
        "ORDER BY 2 DESC\n"
    )


def build_screen_count_sql(table: str, window, services) -> str:
    """화면(`service_code/Pageview name`)별 건수."""
    value = (
        "c_service_code || '/' || "
        "coalesce(nullif(trim(action.name), ''), '(none)')"
    )
    return _count_sql(table, window, services, value, ["action.type = 'Pageview'"])


def build_layer1_count_sql(table: str, window, services) -> str:
    value = "nullif(trim(click.layer1), '')"
    return _count_sql(
        table, window, services, value,
        ["nullif(trim(click.layer1), '') IS NOT NULL"],
    )


def build_layer2_count_sql(table: str, window, services) -> str:
    value = (
        "nullif(trim(click.layer1), '') || '>' || "
        "coalesce(nullif(trim(click.layer2), ''), '(none)')"
    )
    return _count_sql(
        table, window, services, value,
        ["nullif(trim(click.layer1), '') IS NOT NULL"],
    )


def build_version_count_sql(table: str, window, services) -> str:
    value = "nullif(trim(env.app_version), '')"
    return _count_sql(
        table, window, services, value,
        ["nullif(trim(env.app_version), '') IS NOT NULL"],
    )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_state_sql.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/cube/state_sql.py tests/analytics/test_state_sql.py
git commit -m "feat: add state dictionary source counts SQL"
```

---

### Task 8: 큐브 캐시 키와 경로 (`analytics/cube/store.py`)

**Files:**
- Create: `analytics/cube/store.py`
- Create: `tests/analytics/test_store.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_store.py`:

```python
import pandas as pd

from analytics.cube.store import cube_key, cube_path, has_cube, read_cube, write_cube

KW = dict(
    source_version="sv1",
    state_dict_version="sd_abc",
    axes=("period", "os"),
    cube_name="transition",
)


def test_cube_key_is_stable():
    assert cube_key(**KW) == cube_key(**KW)


def test_cube_key_changes_with_source_version():
    assert cube_key(**KW) != cube_key(**{**KW, "source_version": "sv2"})


def test_cube_key_changes_with_state_dict_version():
    assert cube_key(**KW) != cube_key(**{**KW, "state_dict_version": "sd_xyz"})


def test_cube_key_changes_with_axes():
    assert cube_key(**KW) != cube_key(**{**KW, "axes": ("period",)})


def test_cube_key_changes_with_cube_name():
    assert cube_key(**KW) != cube_key(**{**KW, "cube_name": "session"})


def test_cube_path_partitions_by_date_under_the_key(config):
    path = cube_path(config, date="2026-07-27", **KW)
    assert path.name == "date=2026-07-27.parquet"
    assert cube_key(**KW) in str(path)
    assert "transition" in str(path)


def test_has_cube_is_false_before_write_and_true_after(config):
    assert has_cube(config, date="2026-07-27", **KW) is False
    write_cube(config, pd.DataFrame({"cnt": [1]}), date="2026-07-27", **KW)
    assert has_cube(config, date="2026-07-27", **KW) is True


def test_write_cube_roundtrips_the_frame(config):
    df = pd.DataFrame({"from_state": ["a"], "to_state": ["b"], "cnt": [3]})
    path = write_cube(config, df, date="2026-07-27", **KW)
    assert pd.read_parquet(path).equals(df)


def test_different_dates_do_not_collide(config):
    write_cube(config, pd.DataFrame({"cnt": [1]}), date="2026-07-27", **KW)
    assert has_cube(config, date="2026-07-28", **KW) is False


def test_read_cube_concatenates_the_requested_dates(config):
    write_cube(config, pd.DataFrame({"cnt": [1]}), date="2026-07-27", **KW)
    write_cube(config, pd.DataFrame({"cnt": [2]}), date="2026-07-28", **KW)
    df = read_cube(config, dates=["2026-07-27", "2026-07-28"], **KW)
    assert sorted(df["cnt"].tolist()) == [1, 2]


def test_read_cube_skips_dates_that_were_never_built(config):
    write_cube(config, pd.DataFrame({"cnt": [1]}), date="2026-07-27", **KW)
    df = read_cube(config, dates=["2026-07-27", "2026-07-28"], **KW)
    assert df["cnt"].tolist() == [1]


def test_read_cube_with_no_built_dates_returns_empty(config):
    df = read_cube(config, dates=["2026-07-27"], **KW)
    assert df.empty
```

`read_cube` 는 `write_cube` 의 짝이다. 이게 없으면 큐브를 만들어 두고 읽을 방법이 없다.
Phase 2의 `metrics/` 는 이 함수로 큐브를 받아 계산한다.

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.cube.store'`

- [ ] **Step 3: 구현**

`analytics/cube/store.py`:

```python
"""큐브 parquet의 캐시 키와 경로 규약.

캐시 키에 source/state 사전/축/큐브명을 모두 넣으므로, 어느 하나가 달라지면 다른
파일이 된다. 조용한 덮어쓰기가 구조적으로 불가능하다.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_layer.config import Config
from data_layer.util import content_hash


def cube_key(
    source_version: str,
    state_dict_version: str,
    axes: tuple[str, ...],
    cube_name: str,
) -> str:
    return content_hash(source_version, state_dict_version, list(axes), cube_name)


def cube_dir(
    config: Config,
    source_version: str,
    state_dict_version: str,
    axes: tuple[str, ...],
    cube_name: str,
) -> Path:
    key = cube_key(source_version, state_dict_version, axes, cube_name)
    return config.root / "cubes" / cube_name / key


def cube_path(
    config: Config,
    date: str,
    source_version: str,
    state_dict_version: str,
    axes: tuple[str, ...],
    cube_name: str,
) -> Path:
    d = cube_dir(config, source_version, state_dict_version, axes, cube_name)
    return d / f"date={date}.parquet"


def has_cube(config: Config, date: str, **key_parts) -> bool:
    return cube_path(config, date=date, **key_parts).exists()


def write_cube(config: Config, df: pd.DataFrame, date: str, **key_parts) -> Path:
    path = cube_path(config, date=date, **key_parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def read_cube(config: Config, dates: list[str], **key_parts) -> pd.DataFrame:
    """요청한 날짜들의 큐브를 하나의 DataFrame으로 읽는다.

    빌드되지 않은 날짜는 조용히 건너뛴다 — 부분 빌드 상태에서도 있는 만큼 읽을 수
    있어야 한다. 무엇이 없는지는 호출자가 `has_cube` 로 확인한다.
    """
    paths = [
        str(cube_path(config, date=d, **key_parts))
        for d in dates
        if has_cube(config, date=d, **key_parts)
    ]
    if not paths:
        return pd.DataFrame()
    con = duckdb.connect()
    try:
        return con.execute(
            "SELECT * FROM read_parquet($paths)", {"paths": paths}
        ).df()
    finally:
        con.close()
```

`store.py` 상단 import 에 `import duckdb` 를 추가한다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_store.py -q`
Expected: PASS (12 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/cube/store.py tests/analytics/test_store.py
git commit -m "feat: add cube cache key and parquet path convention"
```

---

### Task 9: session 큐브 SQL

**Files:**
- Create: `analytics/cube/sql.py`
- Create: `tests/analytics/test_cube_sql_session.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_cube_sql_session.py`:

```python
from analytics.cube.axes import CORE_AXIS_NAMES
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import build_session_cube_sql

EVENTS = "bigdata_omega_common_iceberg.axz_tiara.all_tiara_n"
DEM = "hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2"
ARGS = dict(
    events_table=EVENTS,
    demography_table=DEM,
    date="2026-07-27",
    next_date="2026-07-28",
    services=["top", "media"],
    versions=["9.5.1", "9.5.0"],
)


def test_session_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_session_cube_sql(**ARGS))


def test_reads_the_day_and_the_next_day():
    sql = build_session_cube_sql(**ARGS)
    assert "date_id IN ('2026-07-27', '2026-07-28')" in sql


def test_keeps_only_sessions_starting_on_the_target_date():
    sql = build_session_cube_sql(**ARGS)
    assert "HAVING" in sql
    assert "min(ts)" in sql
    assert "'2026-07-27'" in sql


def test_attributes_axes_by_first_event():
    sql = build_session_cube_sql(**ARGS)
    assert "min_by(" in sql


def test_emits_every_core_axis():
    sql = build_session_cube_sql(**ARGS)
    for axis in CORE_AXIS_NAMES:
        assert axis in sql


def test_emits_the_session_measures():
    sql = build_session_cube_sql(**ARGS)
    for measure in ("sessions", "uv", "pv", "events", "duration_sum"):
        assert f"AS {measure}" in sql


def test_uses_grouping_sets_so_uv_is_never_summed_downstream():
    sql = build_session_cube_sql(**ARGS)
    assert "GROUPING SETS" in sql


def test_joins_demography_with_a_left_join():
    sql = build_session_cube_sql(**ARGS)
    assert "LEFT JOIN" in sql
    assert DEM in sql


def test_counts_distinct_uuid_for_uv():
    sql = build_session_cube_sql(**ARGS)
    assert "count(DISTINCT" in sql
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_cube_sql_session.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.cube.sql'`

- [ ] **Step 3: 구현**

`analytics/cube/sql.py`:

```python
"""큐브 집계 SQL. 서버에 테이블을 만들지 않고 CTE 단일 SELECT로 수행한다.

세션은 첫 이벤트 날짜에 귀속하므로 날짜 D 빌드는 date_id IN (D, D+1) 을 읽고
첫 이벤트가 D 인 세션만 채택한다. 축 값도 첫 이벤트 기준(min_by)이다.
"""
from __future__ import annotations

from analytics.cube.axes import CORE_AXIS_NAMES, core_axis_selects
from analytics.cube.state_sql import BASE_FILTERS, _in_list, _lit


def _event_cte(
    events_table: str,
    demography_table: str,
    date: str,
    next_date: str,
    services: list[str],
    versions: list[str],
) -> str:
    """(D, D+1) 이벤트에 성연령을 붙이고 축을 계산한 CTE."""
    axis_selects = ",\n    ".join(core_axis_selects(versions))
    conds = "\n      AND ".join(
        [
            f"date_id IN ({_in_list([date, next_date])})",
            f"c_service_code IN ({_in_list(services)})",
            *BASE_FILTERS,
        ]
    )
    return (
        "WITH ev AS (\n"
        "  SELECT\n"
        f"    {axis_selects},\n"
        "    user.uuid AS uuid,\n"
        "    user.suid AS suid,\n"
        "    try_cast(common.access_time AS timestamp) AS ts,\n"
        "    action.type AS action_type,\n"
        "    action.kind AS action_kind,\n"
        "    action.name AS action_name,\n"
        "    c_service_code AS service_code,\n"
        "    common.page AS page,\n"
        "    click.layer1 AS layer1,\n"
        "    click.layer2 AS layer2,\n"
        "    try(cast(usage.duration AS double)) AS usage_duration\n"
        f"  FROM {events_table}\n"
        f"  LEFT JOIN {demography_table} d ON d.uuid = user.uuid\n"
        f"  WHERE {conds}\n"
        ")"
    )


def _grouping_sets(axes: tuple[str, ...]) -> str:
    """전체 조합 + 축을 하나씩 ALL로 접은 조합 + 전체 롤업.

    uv 는 가산이 아니므로 클라이언트가 합산할 수 없다. 자주 쓰는 롤업을 미리 만든다.
    """
    full = "(" + ", ".join(axes) + ")"
    folded = [
        "(" + ", ".join(a for a in axes if a != drop) + ")"
        for drop in axes
        if drop != "period"
    ]
    period_only = "(period)"
    sets = [full, *folded, period_only, "()"]
    return "GROUPING SETS (\n    " + ",\n    ".join(sets) + "\n  )"


def build_session_cube_sql(
    events_table: str,
    demography_table: str,
    date: str,
    next_date: str,
    services: list[str],
    versions: list[str],
) -> str:
    axes = CORE_AXIS_NAMES
    axis_list = ", ".join(axes)
    first_axes = ",\n    ".join(f"min_by({a}, ts) AS {a}" for a in axes)
    return (
        _event_cte(events_table, demography_table, date, next_date, services, versions)
        + ",\nsess AS (\n"
        "  SELECT\n"
        "    uuid,\n"
        "    suid,\n"
        f"    {first_axes},\n"
        "    count(*) AS events,\n"
        "    count_if(action_type = 'Pageview') AS pv,\n"
        "    date_diff('second', min(ts), max(ts)) AS duration_sec\n"
        "  FROM ev\n"
        "  GROUP BY uuid, suid\n"
        f"  HAVING date(min(ts)) = date({_lit(date)})\n"
        ")\n"
        "SELECT\n"
        f"  {axis_list},\n"
        "  count(*) AS sessions,\n"
        "  count(DISTINCT uuid) AS uv,\n"
        "  sum(pv) AS pv,\n"
        "  sum(events) AS events,\n"
        "  sum(duration_sec) AS duration_sum\n"
        "FROM sess\n"
        "GROUP BY " + _grouping_sets(axes) + "\n"
    )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_cube_sql_session.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/cube/sql.py tests/analytics/test_cube_sql_session.py
git commit -m "feat: add session cube SQL with first-event attribution and rollups"
```

---

### Task 10: transition 큐브 SQL

**Files:**
- Modify: `analytics/cube/sql.py`
- Create: `tests/analytics/test_cube_sql_transition.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_cube_sql_transition.py`:

```python
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import build_transition_cube_sql

ARGS = dict(
    events_table="bigdata_omega_common_iceberg.axz_tiara.all_tiara_n",
    demography_table="hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2",
    date="2026-07-27",
    next_date="2026-07-28",
    services=["top"],
    versions=["9.5.1"],
    screens=["top/홈탭_진입", "top/콘텐츠탭_진입"],
)


def test_transition_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_transition_cube_sql(**ARGS))


def test_uses_pageview_rows_as_screens():
    sql = build_transition_cube_sql(**ARGS)
    assert "action_type = 'Pageview'" in sql


def test_screens_outside_the_dictionary_fold_into_other():
    sql = build_transition_cube_sql(**ARGS)
    assert "'/other'" in sql
    assert "'top/홈탭_진입'" in sql


def test_adds_explicit_start_and_exit_states():
    sql = build_transition_cube_sql(**ARGS)
    assert "'START'" in sql
    assert "'EXIT'" in sql


def test_orders_events_within_a_session():
    sql = build_transition_cube_sql(**ARGS)
    assert "PARTITION BY uuid, suid" in sql
    assert "ORDER BY ts" in sql


def test_emits_from_to_cnt_and_duration():
    sql = build_transition_cube_sql(**ARGS)
    for col in ("from_state", "to_state", "cnt", "dur_sum"):
        assert col in sql


def test_keeps_only_sessions_starting_on_the_target_date():
    sql = build_transition_cube_sql(**ARGS)
    assert "'2026-07-27'" in sql


def test_screen_list_escapes_single_quotes():
    args = {**ARGS, "screens": ["top/o'hara"]}
    assert "o''hara" in build_transition_cube_sql(**args)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_cube_sql_transition.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_transition_cube_sql'`

- [ ] **Step 3: 구현 추가**

`analytics/cube/sql.py` 끝에 추가:

```python
def build_transition_cube_sql(
    events_table: str,
    demography_table: str,
    date: str,
    next_date: str,
    services: list[str],
    versions: list[str],
    screens: list[str],
) -> str:
    """화면 전이 큐브. START/EXIT를 명시 상태로 추가한다."""
    axes = CORE_AXIS_NAMES
    axis_list = ", ".join(axes)
    first_axes = ",\n        ".join(f"min_by({a}, ts) AS {a}" for a in axes)
    screen_raw = "service_code || '/' || coalesce(nullif(trim(action_name), ''), '(none)')"
    if screens:
        screen_expr = (
            f"CASE WHEN {screen_raw} IN ({_in_list(screens)})\n"
            f"         THEN {screen_raw}\n"
            "         ELSE service_code || '/other' END"
        )
    else:
        screen_expr = "service_code || '/other'"
    return (
        _event_cte(events_table, demography_table, date, next_date, services, versions)
        + ",\nscreens AS (\n"
        "  SELECT uuid, suid, ts, usage_duration,\n"
        f"    {screen_expr} AS state,\n"
        f"    {axis_list}\n"
        "  FROM ev\n"
        "  WHERE action_type = 'Pageview'\n"
        "),\n"
        "kept AS (\n"
        "  SELECT uuid, suid,\n"
        f"        {first_axes}\n"
        "  FROM screens\n"
        "  GROUP BY uuid, suid\n"
        f"  HAVING date(min(ts)) = date({_lit(date)})\n"
        "),\n"
        "seq AS (\n"
        "  SELECT s.uuid, s.suid, s.ts, s.state, s.usage_duration,\n"
        "    row_number() OVER (PARTITION BY s.uuid, s.suid ORDER BY s.ts) AS rn,\n"
        "    lead(s.state) OVER (PARTITION BY s.uuid, s.suid ORDER BY s.ts) AS next_state\n"
        "  FROM screens s\n"
        "  JOIN kept k ON k.uuid = s.uuid AND k.suid = s.suid\n"
        "),\n"
        "edges AS (\n"
        "  SELECT uuid, suid, state AS from_state,\n"
        "         coalesce(next_state, 'EXIT') AS to_state, usage_duration\n"
        "  FROM seq\n"
        "  UNION ALL\n"
        "  SELECT uuid, suid, 'START' AS from_state, state AS to_state, 0.0\n"
        "  FROM seq WHERE rn = 1\n"
        ")\n"
        "SELECT\n"
        f"  k.{', k.'.join(axes)},\n"
        "  e.from_state,\n"
        "  e.to_state,\n"
        "  count(*) AS cnt,\n"
        "  coalesce(sum(e.usage_duration), 0) AS dur_sum\n"
        "FROM edges e\n"
        "JOIN kept k ON k.uuid = e.uuid AND k.suid = e.suid\n"
        f"GROUP BY k.{', k.'.join(axes)}, e.from_state, e.to_state\n"
    )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_cube_sql_transition.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/cube/sql.py tests/analytics/test_cube_sql_transition.py
git commit -m "feat: add transition cube SQL with explicit START/EXIT states"
```

---

### Task 11: quality 큐브 SQL

**Files:**
- Modify: `analytics/cube/sql.py`
- Create: `tests/analytics/test_cube_sql_quality.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_cube_sql_quality.py`:

```python
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import QUALITY_CHECKS, build_quality_cube_sql

ARGS = dict(
    events_table="bigdata_omega_common_iceberg.axz_tiara.all_tiara_n",
    date="2026-07-27",
    services=["top", "media"],
)


def test_quality_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_quality_cube_sql(**ARGS))


def test_declares_the_five_checks_from_the_spec():
    assert QUALITY_CHECKS == (
        "null_action_name",
        "pageview_null_kind",
        "screen_other_ratio",
        "session_no_screen",
        "page_name_ambiguous",
    )


def test_every_check_appears_in_the_sql():
    sql = build_quality_cube_sql(**ARGS)
    for check in QUALITY_CHECKS:
        assert f"'{check}'" in sql


def test_emits_check_name_violated_total():
    sql = build_quality_cube_sql(**ARGS)
    for col in ("check_name", "violated", "total"):
        assert f"AS {col}" in sql


def test_groups_by_service_code_so_per_service_variance_is_visible():
    sql = build_quality_cube_sql(**ARGS)
    assert "service_code" in sql


def test_does_not_apply_the_invalid_filter_because_it_measures_quality():
    sql = build_quality_cube_sql(**ARGS)
    assert "tag.is_invalid, '0') <> '1'" not in sql
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_cube_sql_quality.py -q`
Expected: FAIL — `ImportError: cannot import name 'QUALITY_CHECKS'`

- [ ] **Step 3: 구현 추가**

`analytics/cube/sql.py` 끝에 추가:

```python
QUALITY_CHECKS = (
    "null_action_name",
    "pageview_null_kind",
    "screen_other_ratio",
    "session_no_screen",
    "page_name_ambiguous",
)


def build_quality_cube_sql(events_table: str, date: str, services: list[str]) -> str:
    """정합성 검사 큐브.

    품질 자체를 재는 쿼리이므로 `tag.is_invalid` 필터를 적용하지 않는다. 필터를 걸면
    측정 대상이 사라진다.
    """
    where = (
        f"date_id IN ({_in_list([date])})\n"
        f"      AND c_service_code IN ({_in_list(services)})\n"
        "      AND NULLIF(TRIM(user.uuid), '') IS NOT NULL\n"
        "      AND NULLIF(TRIM(user.suid), '') IS NOT NULL"
    )
    return (
        "WITH ev AS (\n"
        "  SELECT\n"
        "    c_service_code AS service_code,\n"
        "    coalesce(env.app_version, 'unknown') AS app_version,\n"
        "    user.uuid AS uuid,\n"
        "    user.suid AS suid,\n"
        "    action.type AS action_type,\n"
        "    action.kind AS action_kind,\n"
        "    nullif(trim(action.name), '') AS action_name,\n"
        "    nullif(trim(common.page), '') AS page\n"
        f"  FROM {events_table}\n"
        f"  WHERE {where}\n"
        "),\n"
        "row_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(action_name IS NULL) AS null_action_name,\n"
        "    count_if(action_type = 'Pageview' AND action_kind IS NULL)"
        " AS pageview_null_kind\n"
        "  FROM ev GROUP BY 1, 2\n"
        "),\n"
        "sess AS (\n"
        "  SELECT service_code, app_version, uuid, suid,\n"
        "    count_if(action_type = 'Pageview') AS pv\n"
        "  FROM ev GROUP BY 1, 2, 3, 4\n"
        "),\n"
        "sess_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(pv = 0) AS session_no_screen\n"
        "  FROM sess GROUP BY 1, 2\n"
        "),\n"
        "name_pages AS (\n"
        "  SELECT service_code, app_version, action_name,\n"
        "    count(DISTINCT page) AS pages\n"
        "  FROM ev WHERE action_type = 'Pageview' AND action_name IS NOT NULL\n"
        "  GROUP BY 1, 2, 3\n"
        "),\n"
        "page_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(pages > 1) AS page_name_ambiguous\n"
        "  FROM name_pages GROUP BY 1, 2\n"
        "),\n"
        "screen_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(action_name IS NULL) AS screen_other_ratio\n"
        "  FROM ev WHERE action_type = 'Pageview' GROUP BY 1, 2\n"
        ")\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'null_action_name' AS check_name,\n"
        "       null_action_name AS violated, total AS total FROM row_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'pageview_null_kind', pageview_null_kind, total FROM row_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'screen_other_ratio', screen_other_ratio, total FROM screen_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'session_no_screen', session_no_screen, total FROM sess_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'page_name_ambiguous', page_name_ambiguous, total FROM page_checks\n"
    )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_cube_sql_quality.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/cube/sql.py tests/analytics/test_cube_sql_quality.py
git commit -m "feat: add quality cube SQL for the five consistency checks"
```

---

### Task 12: 2단계 빌드 오케스트레이션 (`analytics/cube/builder.py`)

**Files:**
- Create: `analytics/cube/builder.py`
- Create: `tests/analytics/test_builder.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_builder.py`:

```python
import pandas as pd
import pytest

from analytics.cube.builder import build_cubes, build_state_dict
from analytics.cube.state_dict import StateDict


class FakeQuery:
    """SQL 문자열로 어떤 집계인지 판별해 가짜 결과를 준다."""

    def __init__(self):
        self.calls = []

    def __call__(self, sql):
        self.calls.append(sql)
        if "AS value" in sql:
            if "click.layer1" in sql and "'>'" in sql:
                return pd.DataFrame({"value": ["home_main>SLOT"], "cnt": [50_000]})
            if "click.layer1" in sql:
                return pd.DataFrame({"value": ["home_main"], "cnt": [90_000]})
            if "env.app_version" in sql:
                return pd.DataFrame({"value": ["9.5.1", "9.5.0"], "cnt": [80_000, 20_000]})
            return pd.DataFrame({"value": ["top/홈탭_진입"], "cnt": [70_000]})
        if "AS sessions" in sql:
            return pd.DataFrame({"period": ["2026-07-27"], "sessions": [10], "uv": [8]})
        if "AS cnt" in sql and "from_state" in sql:
            return pd.DataFrame({"from_state": ["START"], "to_state": ["top/홈탭_진입"], "cnt": [5]})
        return pd.DataFrame({"check_name": ["null_action_name"], "violated": [1], "total": [10]})


def test_build_state_dict_applies_the_cut_and_returns_a_versioned_dict(config):
    q = FakeQuery()
    sd = build_state_dict(
        config, window=("2026-07-27", "2026-07-27"), services=["top"], query_fn=q
    )
    assert isinstance(sd, StateDict)
    assert sd.screens == ["top/홈탭_진입"]
    assert sd.app_versions == ["9.5.1", "9.5.0"]
    assert sd.version().startswith("sd_")


def test_build_state_dict_persists_it(config):
    sd = build_state_dict(
        config, window=("2026-07-27", "2026-07-27"), services=["top"], query_fn=FakeQuery()
    )
    assert (config.root / "state_dicts" / f"{sd.version()}.json").exists()


def test_build_cubes_writes_one_file_per_cube_per_date(config):
    sd = StateDict(screens=["top/홈탭_진입"], layer1=["home_main"], layer2=[],
                   app_versions=["9.5.1"], cut_ratio=0.95, min_count=10_000)
    written = build_cubes(
        config, state_dict=sd, window=("2026-07-27", "2026-07-28"),
        services=["top"], source_version="sv1", query_fn=FakeQuery(),
    )
    assert len(written) == 6  # 3 큐브 x 2 날짜
    for path in written:
        assert path.exists()


def test_build_cubes_skips_dates_already_built(config):
    sd = StateDict(screens=["s"], layer1=[], layer2=[], app_versions=["9.5.1"],
                   cut_ratio=0.95, min_count=10_000)
    kw = dict(config=config, state_dict=sd, window=("2026-07-27", "2026-07-27"),
              services=["top"], source_version="sv1")
    build_cubes(**kw, query_fn=FakeQuery())
    second = FakeQuery()
    written = build_cubes(**kw, query_fn=second)
    assert written == []
    assert second.calls == []


def test_build_cubes_refresh_rebuilds(config):
    sd = StateDict(screens=["s"], layer1=[], layer2=[], app_versions=["9.5.1"],
                   cut_ratio=0.95, min_count=10_000)
    kw = dict(config=config, state_dict=sd, window=("2026-07-27", "2026-07-27"),
              services=["top"], source_version="sv1")
    build_cubes(**kw, query_fn=FakeQuery())
    written = build_cubes(**kw, query_fn=FakeQuery(), refresh=True)
    assert len(written) == 3


def test_build_cubes_rejects_unpruned_sql(config):
    sd = StateDict(screens=["s"], layer1=[], layer2=[], app_versions=[],
                   cut_ratio=0.95, min_count=10_000)

    def bad_builder(**kwargs):
        return "SELECT 1"

    with pytest.raises(Exception):
        build_cubes(
            config, state_dict=sd, window=("2026-07-27", "2026-07-27"),
            services=["top"], source_version="sv1", query_fn=FakeQuery(),
            cube_builders={"broken": bad_builder},
        )
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_builder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.cube.builder'`

- [ ] **Step 3: 구현**

`analytics/cube/builder.py`:

```python
"""큐브 빌드 오케스트레이션.

1단계: state 사전을 기간 전체 기준으로 확정하고 저장한다.
2단계: 사전을 고정한 채 날짜별로 큐브를 빌드한다. 이미 있는 (날짜, 캐시키) 조합은
       건너뛰므로 나중에 날짜를 추가해도 앞선 날짜를 다시 만들지 않는다.

`query_fn(sql) -> DataFrame` 이 유일한 서버 I/O 심(seam)이다. 테스트에서 대체한다.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from pathlib import Path

import pandas as pd

from analytics.cube.axes import CORE_AXIS_NAMES
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import (
    build_quality_cube_sql,
    build_session_cube_sql,
    build_transition_cube_sql,
)
from analytics.cube.state_dict import (
    DEFAULT_CUT_RATIO,
    DEFAULT_MIN_COUNT,
    StateDict,
    apply_cut,
    save_state_dict,
)
from analytics.cube.state_sql import (
    build_layer1_count_sql,
    build_layer2_count_sql,
    build_screen_count_sql,
    build_version_count_sql,
)
from analytics.cube.store import has_cube, write_cube
from data_layer.config import Config
from data_layer.util import day_strings

EVENTS_TABLE = "bigdata_omega_common_iceberg.axz_tiara.all_tiara_n"
DEMOGRAPHY_TABLE = "hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2"


def _default_query(sql: str) -> pd.DataFrame:
    """실 Trino 실행. `data_layer.fetch_aggregate._default_query` 와 같은 경로."""
    from data_layer.connection import connect
    from data_layer.sources import load_sources

    src = load_sources(Path("examples/config/sources.json"))["events"]
    conn = connect(src)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


def _run(query_fn, sql: str) -> pd.DataFrame:
    assert_safe_sql(sql)
    return query_fn(sql)


def build_state_dict(
    config: Config,
    window: tuple[str, str],
    services: list[str],
    cut_ratio: float = DEFAULT_CUT_RATIO,
    min_count: int = DEFAULT_MIN_COUNT,
    query_fn=None,
) -> StateDict:
    """1단계. 기간 전체를 한 번 훑어 채택 목록을 확정하고 저장한다."""
    q = query_fn or _default_query
    screens = apply_cut(
        _run(q, build_screen_count_sql(EVENTS_TABLE, window, services)),
        cut_ratio, min_count,
    )
    layer1 = apply_cut(
        _run(q, build_layer1_count_sql(EVENTS_TABLE, window, services)),
        cut_ratio, min_count,
    )
    layer2 = apply_cut(
        _run(q, build_layer2_count_sql(EVENTS_TABLE, window, services)),
        cut_ratio, min_count,
    )
    versions = apply_cut(
        _run(q, build_version_count_sql(EVENTS_TABLE, window, services)),
        cut_ratio, min_count,
    )[:16]
    sd = StateDict(
        screens=screens, layer1=layer1, layer2=layer2, app_versions=versions,
        cut_ratio=cut_ratio, min_count=min_count,
    )
    save_state_dict(config, sd)
    return sd


def _next_day(day: str) -> str:
    return (_date.fromisoformat(day) + timedelta(days=1)).isoformat()


def _session_builder(*, state_dict, date, services, **_):
    return build_session_cube_sql(
        events_table=EVENTS_TABLE, demography_table=DEMOGRAPHY_TABLE,
        date=date, next_date=_next_day(date), services=services,
        versions=state_dict.app_versions,
    )


def _transition_builder(*, state_dict, date, services, **_):
    return build_transition_cube_sql(
        events_table=EVENTS_TABLE, demography_table=DEMOGRAPHY_TABLE,
        date=date, next_date=_next_day(date), services=services,
        versions=state_dict.app_versions, screens=state_dict.screens,
    )


def _quality_builder(*, date, services, **_):
    return build_quality_cube_sql(
        events_table=EVENTS_TABLE, date=date, services=services
    )


DEFAULT_CUBE_BUILDERS = {
    "session": _session_builder,
    "transition": _transition_builder,
    "quality": _quality_builder,
}


def build_cubes(
    config: Config,
    state_dict: StateDict,
    window: tuple[str, str],
    services: list[str],
    source_version: str,
    query_fn=None,
    refresh: bool = False,
    cube_builders: dict | None = None,
) -> list[Path]:
    """2단계. 날짜별로 큐브를 빌드한다. 이미 있는 조합은 건너뛴다.

    한 날짜가 실패하면 그 날짜만 미기록으로 남고 나머지는 커밋된다. 재실행하면
    실패분만 다시 시도한다.
    """
    q = query_fn or _default_query
    builders = cube_builders or DEFAULT_CUBE_BUILDERS
    written: list[Path] = []
    for day in day_strings(*window):
        for name, builder in builders.items():
            key_parts = dict(
                source_version=source_version,
                state_dict_version=state_dict.version(),
                axes=CORE_AXIS_NAMES,
                cube_name=name,
            )
            if not refresh and has_cube(config, date=day, **key_parts):
                continue
            sql = builder(state_dict=state_dict, date=day, services=services)
            df = _run(q, sql)
            written.append(write_cube(config, df, date=day, **key_parts))
    return written
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_builder.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: 전체 스위트 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 실패 0. 신규 테스트가 모두 포함돼 총 개수가 늘어난다.

- [ ] **Step 6: 커밋**

```bash
git add analytics/cube/builder.py tests/analytics/test_builder.py
git commit -m "feat: orchestrate two-stage cube build with incremental skip"
```

---

### Task 13: 라이브 스모크 테스트

**Files:**
- Create: `tests/integration/test_cube_live.py`

- [ ] **Step 1: 테스트 작성**

`tests/integration/test_cube_live.py`:

```python
"""실 Trino 스모크. 크레덴셜이 없으면 skip한다."""
import os
from pathlib import Path

import pytest

from analytics.cube.builder import build_cubes, build_state_dict
from data_layer.config import Config
from data_layer.sources import load_sources

pytestmark = pytest.mark.integration

DAY = "2026-07-27"
SERVICES = ["weather"]  # 작은 서비스로 스모크 비용을 낮춘다


@pytest.fixture(autouse=True)
def _require_creds():
    if not (os.environ.get("TIARA_ID") and os.environ.get("TIARA_PW")):
        pytest.skip("TIARA_ID/TIARA_PW not set — skipping live cube test")


def test_state_dict_and_cubes_build_against_live_trino(tmp_path):
    config = Config(root=tmp_path / "cache")
    config.ensure_dirs()

    sd = build_state_dict(config, window=(DAY, DAY), services=SERVICES, min_count=1)
    assert sd.screens, "화면이 하나도 채택되지 않았다 — 컷 또는 필터를 확인하라"
    assert sd.app_versions

    written = build_cubes(
        config, state_dict=sd, window=(DAY, DAY), services=SERVICES,
        source_version=load_sources(Path("examples/config/sources.json"))["events"].version(),
    )
    assert len(written) == 3

    import pandas as pd

    session = pd.read_parquet(next(p for p in written if "session" in str(p)))
    assert {"sessions", "uv", "pv", "duration_sum"} <= set(session.columns)
    assert session["sessions"].sum() > 0

    transition = pd.read_parquet(next(p for p in written if "transition" in str(p)))
    assert {"from_state", "to_state", "cnt"} <= set(transition.columns)
    assert (transition["from_state"] == "START").any()
    assert (transition["to_state"] == "EXIT").any()

    quality = pd.read_parquet(next(p for p in written if "quality" in str(p)))
    assert {"check_name", "violated", "total"} <= set(quality.columns)


def test_second_build_is_a_noop(tmp_path):
    config = Config(root=tmp_path / "cache")
    config.ensure_dirs()
    sd = build_state_dict(config, window=(DAY, DAY), services=SERVICES, min_count=1)
    sv = load_sources(Path("examples/config/sources.json"))["events"].version()
    kw = dict(config=config, state_dict=sd, window=(DAY, DAY), services=SERVICES,
              source_version=sv)
    build_cubes(**kw)
    assert build_cubes(**kw) == []
```

- [ ] **Step 2: 크레덴셜 없이 skip 확인**

Run: `.venv/bin/python -m pytest tests/integration/test_cube_live.py -q`
Expected: `2 skipped`

- [ ] **Step 3: 크레덴셜로 실행**

Run:
```bash
TIARA_ID=$(.venv/bin/python -c "import sys; sys.path.insert(0,'/Users/roen.axz-pc/Desktop/리서치/markov'); import env; print(env.TIARA_ID)") \
TIARA_PW=$(.venv/bin/python -c "import sys; sys.path.insert(0,'/Users/roen.axz-pc/Desktop/리서치/markov'); import env; print(env.TIARA_PW)") \
.venv/bin/python -m pytest tests/integration/test_cube_live.py -q -m integration
```
Expected: `2 passed`. 실패하면 SQL 문법·컬럼명 문제이므로 에러 메시지의 컬럼을 `all_tiara_n` 스키마와 대조한다.

- [ ] **Step 4: 전체 스위트 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 실패 0, skip 은 integration 수만큼

- [ ] **Step 5: 커밋**

```bash
git add tests/integration/test_cube_live.py
git commit -m "test: add live smoke for state dict and cube build"
```

---

### Task 14: 실제 하루치 큐브 빌드로 스펙 수치 검증

**Files:**
- Create: `scripts/build_cubes.py`

- [ ] **Step 1: CLI 스크립트 작성**

`scripts/build_cubes.py`:

```python
"""큐브 빌드 CLI.

사용:
    .venv/bin/python scripts/build_cubes.py 2026-07-27 2026-07-27 top,media
"""
from __future__ import annotations

import sys
from pathlib import Path

from analytics.cube.builder import build_cubes, build_state_dict
from data_layer.config import Config
from data_layer.sources import load_sources


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    start, end, services_csv = argv[1], argv[2], argv[3]
    services = [s.strip() for s in services_csv.split(",") if s.strip()]

    config = Config.from_env()
    config.ensure_dirs()
    src = load_sources(Path("examples/config/sources.json"))["events"]

    print(f"[1/2] state 사전 생성 {start}~{end} {services}")
    sd = build_state_dict(config, window=(start, end), services=services)
    print(f"      version={sd.version()} screens={len(sd.screens)} "
          f"layer1={len(sd.layer1)} layer2={len(sd.layer2)} "
          f"versions={len(sd.app_versions)}")

    print("[2/2] 큐브 빌드")
    written = build_cubes(
        config, state_dict=sd, window=(start, end), services=services,
        source_version=src.version(),
    )
    for p in written:
        size_kb = p.stat().st_size / 1024
        print(f"      {p}  ({size_kb:,.0f} KB)")
    if not written:
        print("      (모두 캐시 적중 — 새로 만든 것 없음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 2: 하루치 실행**

Run:
```bash
TIARA_ID=$(.venv/bin/python -c "import sys; sys.path.insert(0,'/Users/roen.axz-pc/Desktop/리서치/markov'); import env; print(env.TIARA_ID)") \
TIARA_PW=$(.venv/bin/python -c "import sys; sys.path.insert(0,'/Users/roen.axz-pc/Desktop/리서치/markov'); import env; print(env.TIARA_PW)") \
.venv/bin/python scripts/build_cubes.py 2026-07-27 2026-07-27 top,media,entertain,sports,content_v,search
```
Expected: state 사전 요약과 3개 parquet 경로·크기가 출력된다.

- [ ] **Step 3: 스펙 수치와 대조**

Run:
```bash
.venv/bin/python - <<'PY'
import glob
import pandas as pd
for name in ("session", "transition", "quality"):
    paths = glob.glob(f"cache/cubes/{name}/*/date=*.parquet")
    df = pd.concat([pd.read_parquet(p) for p in paths])
    print(f"{name:11} rows={len(df):>10,}")
    if name == "transition":
        print("            states:", df["from_state"].nunique())
PY
```
Expected: `transition` 행수가 스펙의 하루 214,368 과 같은 자릿수(10만~40만)여야 한다. 크게 벗어나면 축 표현식이나 세션 귀속 조건을 점검한다. 결과를 실행 보고에 기록한다.

- [ ] **Step 4: 재실행이 캐시 적중인지 확인**

같은 명령을 다시 실행한다.
Expected: `(모두 캐시 적중 — 새로 만든 것 없음)`

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_cubes.py
git commit -m "feat: add cube build CLI and verify measured cube size against spec"
```

---

### Task 15: 표본 시대 잔여 표면 정리와 `query.py` 결정

**출처:** Task 3의 코드 품질 리뷰. 이 두 항목은 Task 3 커밋의 결함이 아니라 그 삭제로
비로소 확정된 인접 부패다. Task 8에서 `read_cube` 가 생긴 뒤에 실행해야 `query.py`
판단이 예측이 아니라 근거를 갖는다. **Task 8 이후, Task 14 이전에 수행한다.**

**Files:**
- Modify: `data_layer/manifest.py`, `data_layer/config.py`, `tests/test_manifest.py`
- Decide (삭제 또는 유지): `data_layer/query.py`, `tests/test_query.py`, `data_layer/__init__.py`

- [ ] **Step 1: 죽은 표면을 재확인**

```bash
grep -rnE "has_event|add_event_partition|event_start_days|add_dim|events_dir|dims_dir" --include='*.py' . | grep -v "\.venv"
```
Expected: `data_layer/manifest.py`, `data_layer/config.py`, `tests/test_manifest.py` 만.
프로덕션 호출자가 나오면 그 항목은 삭제 대상에서 빼고 보고한다.

- [ ] **Step 2: manifest 의 events/dims 표면 삭제**

`data_layer/manifest.py` 에서 `event_start_days`, `has_event`, `add_event_partition`,
`add_dim` 을 삭제하고, `load()` 의 기본 데이터에서 `"events"`·`"dims"` 버킷과 그
`setdefault` 를 제거한다. `results`·`published`·`config` 섹션은 **유지**한다.

- [ ] **Step 3: `config.py` 의 미사용 디렉터리 제거**

`events_dir`·`dims_dir` 프로퍼티와 `ensure_dirs()` 의 해당 항목을 삭제한다.
`results_dir`·`config_dir`·`manifest_path` 는 유지한다.

- [ ] **Step 4: `tests/test_manifest.py` 정리**

삭제된 메서드를 검증하는 테스트를 제거한다. `results`/`published`/`config` 테스트는 유지한다.

- [ ] **Step 5: `query.py` 결정**

이 시점에 `analytics/cube/store.read_cube` 가 존재한다. 다음을 확인한다:

```bash
grep -rnE "from data_layer.query|data_layer\.query|import run" --include='*.py' . | grep -v "\.venv"
```

`query.run` 에 프로덕션 호출자가 **여전히 없고** `read_cube` 가 큐브 읽기를 담당한다면
`data_layer/query.py`·`tests/test_query.py` 를 삭제하고 `data_layer/__init__.py` 의 `run`
export 를 제거한다. 새 호출자가 생겼다면 유지하고 그 호출자를 보고에 적는다.

**판단 근거(리뷰어 의견, 참고용):** `fetch.py` 가 삭제되어 로컬 원본 이벤트를 만드는
경로가 없으므로 "로컬 원본에 임의 SQL 실행"이라는 `query.run` 의 고유 니치는 사라졌다.
`fetch_aggregate` 가 이미 실행+캐시+매니페스트 등록을 담당한다.

- [ ] **Step 6: 스위트 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 실패 0. 삭제한 테스트 수만큼 줄어든다. 정확한 수를 보고에 적는다.

- [ ] **Step 7: 커밋**

```bash
git add -u data_layer tests
git commit -m "refactor: drop the manifest event/dim surface left dead by the sampling removal"
```

`query.py` 를 삭제했다면 별도 커밋으로 분리한다:

```bash
git commit -m "refactor: retire query.py now that read_cube owns cube reads"
```

---

## Self-Review 결과

**스펙 커버리지**

| 스펙 요구 | 태스크 |
|---|---|
| `all_tiara_n` 좌표 이전 | 1 |
| 성연령 소스 선언·조인 | 1, 9 |
| `date.day` 오매핑 제거 | 1 |
| 표본 경로 삭제 | 2 |
| 세션키 `(uuid, suid)` | 3, 9, 10 |
| 코어 7축 | 4 |
| `unknown` 보존 | 4 |
| 앱버전 상위 16 + other | 4, 12 |
| 파티션 프루닝 강제 | 5, 12 |
| `NOT IN` 금지 | 5 |
| state 컷(`cut_ratio`, `min_count`) | 6 |
| state 사전 버전 고정 | 6, 8 |
| 캐시 키(조용한 덮어쓰기 방지) | 8 |
| `session` 큐브 + `uv` 롤업(GROUPING SETS) | 9 |
| 첫 이벤트 귀속·날짜 경계 | 9, 10 |
| `transition` 큐브 + START/EXIT | 10 |
| `quality` 큐브 5검사 | 11 |
| 2단계 빌드·증분 스킵 | 12 |
| 부분 실패 시 성공분만 커밋 | 12 |
| 라이브 스모크 | 13 |
| 실측 대조 | 14 |
| 87 테스트 회귀 가드 | 1~3의 스위트 확인 스텝 |
| 표본 시대 잔여 표면(manifest events/dims, query.py) | 15 |

**스코프 밖(2단계 이후)**: `action`·`cond_transition`·`path` 큐브, `metrics/` 지표 계산,
대시보드, 리포트 팩, `skills/descriptive/` 흡수, `manifest.set_config` 배선.

**타입 정합성**: `cube_key`/`cube_path`/`has_cube`/`write_cube` 는 모두
`source_version`·`state_dict_version`·`axes`·`cube_name` 을 키로 받는다(Task 8, 12 일치).
`StateDict` 필드명 `screens`/`layer1`/`layer2`/`app_versions`/`cut_ratio`/`min_count` 는
Task 6·12·13에서 동일하다. `apply_cut(counts, cut_ratio, min_count)` 는
`value`/`cnt` 컬럼을 받으며 Task 7의 SQL이 그 두 컬럼을 낸다.

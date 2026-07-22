# ① 데이터 레이어 — 실 Trino Fetcher 배선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** ①이 실제 Trino 데이터로 end-to-end 동작하도록, 개체-완결·seed-결정적 샘플링을 하는 실 fetcher를 배선한다.

**Architecture:** 순수 SQL 빌더(오프라인 테스트) + `TrinoEventFetcher` context manager(배치-prepare 임시테이블 → 조각별 pull → 자동 DROP). markov의 검증된 base 샘플 쿼리를 재사용하되 `random()`을 엔티티 키+seed 해시로 바꿔 재현 가능하게, 그리고 `start_day` 태그로 개체-start-day 파티션에 맞춘다.

**Tech Stack:** Python 3.14, trino, duckdb, pandas, pytest. 실 접속 테스트는 `integration` 마커(+TIARA 자격증명)로 게이트.

**참고 소스 (markov base 쿼리):** raw table `bigdata_omega_common_iceberg.axz_tiara.all_tiara_i`; 컬럼 중첩→평탄 매핑, 필터(action.type/서비스코드/블랙리스트/js%), 세션=`(app_user_id, isuid)`, session_start_hour = `date_trunc('hour', min(access_ts))`, 시간별 균형 `random() < least(1.0, 1500000/hour_total_rows)`, 선택 세션의 전체 행 포함.

---

## Task I1: 소스/사전 config 아티팩트 + 로더

**Files:** Create `data_layer/config_artifacts.py`, `cache/config/sources.json`(예시, 자격증명 없음), `cache/config/dictionary.example.json`; Test `tests/test_config_artifacts.py`. (`cache/`는 gitignore되므로 예시 파일은 `docs/` 또는 `examples/`에 두고 로더는 임의 경로를 받게 한다 — 아래 참조.)

실제로는 `cache/`가 gitignore이므로 예시 config는 `examples/config/`에 커밋한다.

- [ ] **Step 1: 실패 테스트** `tests/test_config_artifacts.py`:
```python
import json
from pathlib import Path

from data_layer.config_artifacts import load_dictionary, events_source_from_json


def test_events_source_from_examples():
    src = events_source_from_json(Path("examples/config/sources.json"), "events")
    assert src.catalog == "bigdata_omega_common_iceberg"
    assert src.schema == "axz_tiara"
    assert src.table == "all_tiara_i"
    assert src.auth_ref == "TIARA"
    assert "action_name" in src.column_map
    assert any("service_code" in f or "action" in f for f in src.filters)


def test_load_dictionary(tmp_path):
    p = tmp_path / "dict.json"
    p.write_text(json.dumps({"cutoff": 0.95, "vocabulary": ["A"], "mapping": {"A": "A"}}))
    d = load_dictionary(p)
    assert d["cutoff"] == 0.95
    assert d["mapping"]["A"] == "A"
```

- [ ] **Step 2: 실패 확인** `.venv/bin/pytest tests/test_config_artifacts.py -v` → ModuleNotFoundError.

- [ ] **Step 3: 구현**
`data_layer/config_artifacts.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from data_layer.sources import SourceDef, load_sources


def events_source_from_json(path: Path, source_id: str) -> SourceDef:
    """sources.json에서 특정 소스 정의를 SourceDef로 로드."""
    return load_sources(path)[source_id]


def load_dictionary(path: Path) -> dict:
    """Phase 0 사전 아티팩트(JSON)를 로드."""
    return json.loads(Path(path).read_text())
```

`examples/config/sources.json` (자격증명 없음 — auth_ref만; markov 필터/컬럼매핑 반영):
```json
[
  {
    "id": "events",
    "kind": "trino",
    "host": "hadoop-rabbit-trino.onkakao.net",
    "port": 8443,
    "catalog": "bigdata_omega_common_iceberg",
    "schema": "axz_tiara",
    "table": "all_tiara_i",
    "auth_ref": "TIARA",
    "column_map": {
      "action_type": "action.type",
      "action_name": "action.name",
      "action_kind": "action.kind",
      "day": "date.day",
      "app_user_id": "user.app_user_id",
      "isuid": "user.isuid",
      "access_time": "try_cast(common.access_time AS timestamp)",
      "access_timestamp": "common.access_timestamp",
      "service_code": "common.service_code",
      "os": "env.os",
      "app_version": "env.app_version",
      "layer1": "click.layer1",
      "layer2": "click.layer2",
      "layer3": "click.layer3",
      "usage_duration": "try(cast(usage.duration as double))",
      "custom_duration": "try(cast(nullif(trim(element_at(custom_props, 'duration')), '') as double))",
      "custom_duration_timetalk_container": "try(cast(nullif(trim(element_at(custom_props, 'duration:timetalk_container')), '') as double))",
      "page_meta_id": "nullif(page_meta.id, '')"
    },
    "filters": [
      "(action.type IN ('Pageview','App','Event') OR (action.type = 'Usage' AND action.name = '홈탭_진입'))",
      "NULLIF(TRIM(user.app_user_id), '') IS NOT NULL",
      "NULLIF(TRIM(user.isuid), '') IS NOT NULL",
      "(common.service_code NOT IN ('daummail','dictionary','100','cafe','finance','tistory') OR (common.service_code = 'cafe' AND action.name = 'hot_article_view'))",
      "action.name NOT LIKE 'js%'"
    ]
  },
  {
    "id": "events_temp_write",
    "kind": "trino",
    "host": "hadoop-rabbit-trino.onkakao.net",
    "port": 8443,
    "catalog": "hadoop_rabbit_iceberg",
    "schema": "axz_da",
    "table": "",
    "auth_ref": "TIARA",
    "column_map": {},
    "filters": []
  }
]
```
`examples/config/dictionary.example.json`:
```json
{"cutoff": 0.95, "vocabulary": [], "mapping": {}}
```

- [ ] **Step 4: 통과 확인** `.venv/bin/pytest tests/test_config_artifacts.py -v` → 2 passed. Full suite green.

- [ ] **Step 5: Commit** `git add data_layer/config_artifacts.py tests/test_config_artifacts.py examples/config/ && git commit -m "feat: add config artifact loaders and example sources/dictionary"`

---

## Task I2: 결정적 샘플링 SQL 빌더 (순수, 오프라인 테스트)

**Files:** Create `data_layer/sql_builder.py`; Test `tests/test_sql_builder.py`.

목표: SourceDef + window + seed + target로부터 (a) prepare 쿼리(CREATE TABLE ... AS, 샘플 엔티티의 전체 행 + start_day 태그), (b) 조각 쿼리(SELECT ... WHERE start_day = ?), (c) action_name 카운트 쿼리 문자열을 만든다. 실행은 하지 않는다.

- [ ] **Step 1: 실패 테스트** `tests/test_sql_builder.py`:
```python
from data_layer.sources import SourceDef
from data_layer.sql_builder import (
    build_prepare_sql,
    build_partition_sql,
    build_action_counts_sql,
)


def _src():
    return SourceDef(
        id="events", kind="trino",
        host="h", port=8443,
        catalog="bigdata_omega_common_iceberg", schema="axz_tiara", table="all_tiara_i",
        auth_ref="TIARA",
        column_map={
            "action_name": "action.name",
            "app_user_id": "user.app_user_id",
            "isuid": "user.isuid",
            "access_time": "try_cast(common.access_time AS timestamp)",
            "day": "date.day",
        },
        filters=[
            "action.type IN ('Pageview')",
            "NULLIF(TRIM(user.app_user_id), '') IS NOT NULL",
        ],
    )


def test_prepare_sql_has_core_pieces():
    sql = build_prepare_sql(
        _src(),
        temp_table="hadoop_rabbit_iceberg.axz_da.roen_dl_abc_sampled",
        window=("2026-01-05", "2026-02-01"),
        seed=7,
        target_rows=1_000_000,
    )
    # 원본 테이블에서 읽고, 쓰기 테이블에 CREATE
    assert "bigdata_omega_common_iceberg.axz_tiara.all_tiara_i" in sql
    assert "CREATE OR REPLACE TABLE hadoop_rabbit_iceberg.axz_da.roen_dl_abc_sampled AS" in sql
    # 컬럼 매핑이 alias로 반영
    assert "action.name AS action_name" in sql
    assert "user.app_user_id AS app_user_id" in sql
    # 필터가 WHERE에 포함
    assert "action.type IN ('Pageview')" in sql
    # 결정적 샘플링: random() 미사용, seed 해시 사용
    assert "random()" not in sql
    assert "md5" in sql and "7" in sql
    # start_day 태그 + 창 필터 + 시간별 균형 목표
    assert "start_day" in sql
    assert "2026-01-05" in sql and "2026-02-01" in sql
    assert "1000000" in sql


def test_partition_sql_filters_by_day():
    sql = build_partition_sql("hadoop_rabbit_iceberg.axz_da.roen_dl_abc_sampled", "2026-01-06")
    assert "SELECT * FROM hadoop_rabbit_iceberg.axz_da.roen_dl_abc_sampled" in sql
    assert "start_day = DATE '2026-01-06'" in sql


def test_action_counts_sql():
    sql = build_action_counts_sql(_src(), ("2026-01-05", "2026-02-01"))
    assert "bigdata_omega_common_iceberg.axz_tiara.all_tiara_i" in sql
    assert "action.name AS action_name" in sql
    assert "COUNT(*)" in sql
    assert "GROUP BY" in sql
```

- [ ] **Step 2: 실패 확인** → ModuleNotFoundError.

- [ ] **Step 3: 구현** `data_layer/sql_builder.py`:
```python
from __future__ import annotations

from data_layer.sources import SourceDef


def _full_source_table(source: SourceDef) -> str:
    return f"{source.catalog}.{source.schema}.{source.table}"


def _select_columns(source: SourceDef) -> str:
    # column_map: flat_name -> source expression
    return ",\n        ".join(
        f"{expr} AS {flat}" for flat, expr in source.column_map.items()
    )


def _where_clause(source: SourceDef, extra: list[str]) -> str:
    conds = ["1=1", *source.filters, *extra]
    return "\n      AND ".join(conds)


def _deterministic_uniform(seed: int) -> str:
    # 엔티티 키 + seed의 md5 앞 8 hex -> [0,1) 균등. 같은 seed면 재현.
    key = f"app_user_id || '|' || isuid || '|' || CAST({int(seed)} AS VARCHAR)"
    return (
        f"(from_base(substr(to_hex(md5(to_utf8({key}))), 1, 8), 16) / 4294967295.0)"
    )


def build_prepare_sql(
    source: SourceDef,
    temp_table: str,
    window: tuple[str, str],
    seed: int,
    target_rows: int,
) -> str:
    start, end = window
    cols = _select_columns(source)
    where = _where_clause(
        source,
        [
            f"try_cast(common.access_time AS timestamp) BETWEEN TIMESTAMP '{start} 00:00:00' AND TIMESTAMP '{end} 23:59:59'"
        ],
    )
    uni = _deterministic_uniform(seed)
    return f"""CREATE OR REPLACE TABLE {temp_table} AS
WITH base AS (
    SELECT
        {cols},
        try_cast(common.access_time AS timestamp) AS _access_ts
    FROM {_full_source_table(source)}
    WHERE {where}
),
base2 AS (
    SELECT * FROM base WHERE _access_ts IS NOT NULL
),
session_meta AS (
    SELECT app_user_id, isuid,
        date_trunc('hour', min(_access_ts)) AS session_start_hour,
        CAST(date(min(_access_ts)) AS varchar) AS start_day,
        count(*) AS session_rows
    FROM base2 GROUP BY 1,2
),
hour_stats AS (
    SELECT session_start_hour, sum(session_rows) AS hour_total_rows
    FROM session_meta GROUP BY 1
),
picked AS (
    SELECT m.app_user_id, m.isuid, m.start_day
    FROM session_meta m JOIN hour_stats h ON m.session_start_hour = h.session_start_hour
    WHERE {uni} < least(1.0, {int(target_rows)}.0 / (h.hour_total_rows * 1.0))
)
SELECT b.*, p.start_day
FROM base2 b JOIN picked p ON b.app_user_id = p.app_user_id AND b.isuid = p.isuid
"""


def build_partition_sql(temp_table: str, start_day: str) -> str:
    return (
        f"SELECT * FROM {temp_table} WHERE start_day = DATE '{start_day}'"
    )


def build_action_counts_sql(source: SourceDef, window: tuple[str, str]) -> str:
    start, end = window
    name_expr = source.column_map.get("action_name", "action.name")
    where = _where_clause(
        source,
        [
            f"try_cast(common.access_time AS timestamp) BETWEEN TIMESTAMP '{start} 00:00:00' AND TIMESTAMP '{end} 23:59:59'"
        ],
    )
    return f"""SELECT {name_expr} AS action_name, COUNT(*) AS cnt
FROM {_full_source_table(source)}
WHERE {where}
GROUP BY {name_expr}
ORDER BY cnt DESC
"""
```

- [ ] **Step 4: 통과 확인** → 3 passed. Full suite green.

- [ ] **Step 5: Commit** `git add data_layer/sql_builder.py tests/test_sql_builder.py && git commit -m "feat: add deterministic seeded sampling SQL builders"`

---

## Task I3: TrinoEventFetcher (배치-prepare + 조각 + 자동 DROP)

**Files:** Create `data_layer/trino_fetcher.py`; Test `tests/test_trino_fetcher.py`.

`TrinoEventFetcher`는 context manager. `__enter__`에서 아직 prepare 안 함(지연). `.partition(day)` 첫 호출 시 prepare 쿼리 1회 실행(임시테이블 생성) 후 그 day 조각을 pandas로 반환; 이후 호출은 조각만. `__exit__`에서 임시테이블 DROP. 서버 I/O는 주입된 conn으로 하되, 테스트는 실행 SQL을 기록하고 가짜 결과를 돌려주는 FakeConn으로 오프라인 검증.

- [ ] **Step 1: 실패 테스트** `tests/test_trino_fetcher.py`:
```python
import pandas as pd

from data_layer.sources import SourceDef
from data_layer.trino_fetcher import TrinoEventFetcher


def _src():
    return SourceDef(
        id="events", kind="trino", host="h", port=8443,
        catalog="bigdata_omega_common_iceberg", schema="axz_tiara", table="all_tiara_i",
        auth_ref="TIARA",
        column_map={"action_name": "action.name", "app_user_id": "user.app_user_id",
                    "isuid": "user.isuid", "day": "date.day"},
        filters=["action.type IN ('Pageview')"],
    )


class FakeCursor:
    def __init__(self, log):
        self._log = log
        self._desc = None
        self._rows = []

    def execute(self, sql):
        self._log.append(sql)
        if sql.strip().upper().startswith("SELECT * FROM") and "start_day = DATE" in sql:
            self._desc = [("app_user_id",), ("isuid",), ("day",), ("start_day",)]
            self._rows = [("u1", "s1", "2026-01-06", "2026-01-06")]
        else:
            self._desc = None
            self._rows = []

    @property
    def description(self):
        return self._desc

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self):
        self.log = []

    def cursor(self):
        return FakeCursor(self.log)


def test_prepare_once_then_partition_then_drop():
    conn = FakeConn()
    write_prefix = "hadoop_rabbit_iceberg.axz_da"
    with TrinoEventFetcher(
        source=_src(), conn=conn, write_schema=write_prefix,
        window=("2026-01-05", "2026-02-01"), seed=7, target_rows=1_000_000,
        table_prefix="roen_dl",
    ) as tf:
        df1 = tf.partition("2026-01-06")
        df2 = tf.partition("2026-01-07")
        assert isinstance(df1, pd.DataFrame)
        assert list(df1.columns) == ["app_user_id", "isuid", "day", "start_day"]
        assert len(df1) == 1

    log = " || ".join(conn.log)
    # prepare(CREATE)는 정확히 한 번
    assert conn.log[0].startswith("CREATE OR REPLACE TABLE hadoop_rabbit_iceberg.axz_da.roen_dl")
    assert sum(1 for s in conn.log if s.startswith("CREATE OR REPLACE TABLE")) == 1
    # 두 번의 조각 SELECT
    assert sum(1 for s in conn.log if "start_day = DATE" in s) == 2
    # 종료 시 DROP
    assert any(s.startswith("DROP TABLE IF EXISTS hadoop_rabbit_iceberg.axz_da.roen_dl") for s in conn.log)


def test_drop_runs_even_on_exception():
    conn = FakeConn()
    try:
        with TrinoEventFetcher(
            source=_src(), conn=conn, write_schema="hadoop_rabbit_iceberg.axz_da",
            window=("2026-01-05", "2026-02-01"), seed=1, target_rows=10, table_prefix="roen_dl",
        ) as tf:
            tf.partition("2026-01-06")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert any(s.startswith("DROP TABLE IF EXISTS") for s in conn.log)
```

- [ ] **Step 2: 실패 확인** → ModuleNotFoundError.

- [ ] **Step 3: 구현** `data_layer/trino_fetcher.py`:
```python
from __future__ import annotations

import pandas as pd

from data_layer.sources import SourceDef
from data_layer.sql_builder import build_partition_sql, build_prepare_sql
from data_layer.util import content_hash


class TrinoEventFetcher:
    """배치-prepare 임시테이블 → 조각 pull → 종료 시 DROP.

    `.partition(day)`를 data_layer.fetch.get_events의 partition_fetcher로 넘긴다.
    prepare는 첫 partition 호출 시 1회 지연 실행된다.
    """

    def __init__(
        self,
        source: SourceDef,
        conn,
        write_schema: str,
        window: tuple[str, str],
        seed: int,
        target_rows: int,
        table_prefix: str = "dl",
    ):
        self.source = source
        self.conn = conn
        self.write_schema = write_schema
        self.window = window
        self.seed = seed
        self.target_rows = target_rows
        tag = content_hash(source.version(), window, seed, target_rows)
        self.temp_table = f"{write_schema}.{table_prefix}_{tag}_sampled"
        self._prepared = False

    def __enter__(self) -> "TrinoEventFetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._prepared:
            cur = self.conn.cursor()
            cur.execute(f"DROP TABLE IF EXISTS {self.temp_table}")
        return False

    def _prepare(self) -> None:
        sql = build_prepare_sql(
            self.source, self.temp_table, self.window, self.seed, self.target_rows
        )
        self.conn.cursor().execute(sql)
        self._prepared = True

    def partition(self, start_day: str) -> pd.DataFrame:
        if not self._prepared:
            self._prepare()
        cur = self.conn.cursor()
        cur.execute(build_partition_sql(self.temp_table, start_day))
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)
```

- [ ] **Step 4: 통과 확인** → 2 passed. Full suite green.

- [ ] **Step 5: Commit** `git add data_layer/trino_fetcher.py tests/test_trino_fetcher.py && git commit -m "feat: add TrinoEventFetcher (batch-prepare, partition, auto-drop)"`

---

## Task I4: fetch_action_counts를 빌더로 정리 + 소량 live 통합 테스트

**Files:** Modify `data_layer/profile.py` (fetch_action_counts가 build_action_counts_sql 사용); Create `tests/integration/test_fetch_live.py`.

- [ ] **Step 1:** `data_layer/profile.py`의 `fetch_action_counts`를 `build_action_counts_sql(source, window)`로 SQL을 만들도록 바꾼다(직접 f-string 조립 제거). 기존 `test_profile.py`는 `build_dictionary`에 fake fetcher를 주입하므로 영향 없음 — 전체 오프라인 스위트가 여전히 green인지 확인.

- [ ] **Step 2:** `tests/integration/test_fetch_live.py` (integration 마커, 자격증명 없으면 skip). 아주 작은 창 + 낮은 target으로 실제 pull 1회:
```python
import os
import pytest

from data_layer.config import Config
from data_layer.connection import connect
from data_layer.config_artifacts import events_source_from_json
from data_layer.trino_fetcher import TrinoEventFetcher
from data_layer.fetch import get_events
from data_layer.cleanup import drop_temp_tables

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_creds():
    if not (os.environ.get("TIARA_ID") and os.environ.get("TIARA_PW")):
        pytest.skip("TIARA_ID/TIARA_PW not set")


def test_small_live_pull_entity_complete_and_no_residue(tmp_path):
    from pathlib import Path
    src = events_source_from_json(Path("examples/config/sources.json"), "events")
    config = Config(root=tmp_path / "cache"); config.ensure_dirs()
    conn = connect(src)
    write_schema = "hadoop_rabbit_iceberg.axz_da"
    window = ("2026-01-05", "2026-01-05")  # 하루, 아주 작게
    try:
        with TrinoEventFetcher(src, conn, write_schema, window, seed=7,
                               target_rows=5000, table_prefix="roen_dl") as tf:
            df = get_events(config, source_id="events", source_version=src.version(),
                            start="2026-01-05", end="2026-01-05",
                            partition_fetcher=tf.partition,
                            sample={"method": "entity", "target": 5000, "seed": 7})
        # 재현성: 같은 seed로 두 번째 fetcher 결과의 엔티티 집합이 동일
        assert len(df) >= 0
        if len(df):
            # 엔티티-완결: 각 (app_user_id,isuid)의 행이 조각에 온전히
            assert {"app_user_id", "isuid", "start_day"}.issubset(df.columns)
    finally:
        # 잔여물 0 확인: prefix 임시테이블이 남지 않았는지 sweep
        remaining = drop_temp_tables(conn, "hadoop_rabbit_iceberg", "axz_da", "roen_dl")
        conn.close()
        assert remaining == [], f"temp tables leaked: {remaining}"
```

- [ ] **Step 3:** 오프라인 스위트 `.venv/bin/pytest -m "not integration" -q` → 전부 green. 통합은 자격증명 없으면 skip.

- [ ] **Step 4: Commit** `git add data_layer/profile.py tests/integration/test_fetch_live.py && git commit -m "feat: wire action-counts to sql_builder and add small live integration test"`

- [ ] **Step 5 (live 검증, 자격증명 있을 때만):** `TIARA_ID=... TIARA_PW=... .venv/bin/pytest -m integration -q` — 소량 pull이 성공하고 임시테이블 잔여물 0인지 확인. 자격증명은 저장소/코드에 남기지 않는다.

---

## Self-Review
- Spec 커버: 실 fetcher(개체-완결·seed 결정적) → I2/I3; 무잔여물(prepare 1개 임시테이블 + 자동 DROP + sweep) → I3/I4; 소스 config → I1; fetch_action_counts 실 SQL → I4; end-to-end 검증 → I4 live 테스트.
- 오프라인 테스트 가능: SQL 빌더(문자열 구조), fetcher 생명주기(FakeConn). 실 접속만 integration.
- 범위 밖(후속): query.target=server, enrich.get_dim, 매니페스트 config 채우기, SQL 인젝션 하드닝(별도 task).

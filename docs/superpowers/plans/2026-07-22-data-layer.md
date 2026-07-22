# 데이터 접근·캐시 레이어 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 분석 스킬들이 `import`해서 쓰는 공용 파이썬 패키지 `data_layer/`를 만든다 — Trino에서 개체-완결 샘플을 뽑아 로컬 parquet에 캐시하고, 서버 잔여물 없이, 모든 분석 결정을 버전 관리 config로 두어 재-pull 없이 재계산 가능하게 한다.

**Architecture:** 3단계(Phase 0 프로파일 → Phase 1 fetch → Phase 2 로컬 DuckDB 연산). 서버는 집계/축소만 하고 결과를 로컬로 내려 캐시한다. 이벤트는 개체 첫이벤트일자로 파티션되어 자정 넘는 세션이 잘리지 않는다. 서버를 건드리는 부분은 주입 가능한 seam으로 분리해 대부분의 테스트를 오프라인(실제 DuckDB + 가짜 fetcher)으로 돌린다.

**Tech Stack:** Python 3.11+, trino(DBAPI + BasicAuthentication), duckdb, pandas, pyarrow(parquet), pytest.

---

## File Structure

```
data_analysis/
  data_layer/
    __init__.py          # 패키지 공개 API 재노출
    util.py              # content_hash, day_strings (순수 헬퍼)
    config.py            # Config: 캐시 경로/디렉터리
    sources.py           # SourceDef, load_sources, resolve_auth, version
    connection.py        # Trino 커넥션 어댑터 (얇음)
    manifest.py          # Manifest 읽기/쓰기/질의
    profile.py           # Phase 0: compute_dictionary(순수) + build_dictionary(서버)
    fetch.py             # Phase 1: missing_start_days, read_partitions, get_events
    enrich.py            # 차원 로컬 조인: join_dim, get_dim
    query.py             # 로컬 DuckDB 실행 + 결과 해시 캐시: run
    cleanup.py           # 서버 임시테이블 정리: filter_prefixed, drop_temp_tables
    convergence.py       # check_convergence
  tests/
    conftest.py
    test_util.py
    test_config.py
    test_sources.py
    test_connection.py
    test_manifest.py
    test_profile.py
    test_fetch.py
    test_enrich.py
    test_query.py
    test_cleanup.py
    test_convergence.py
    integration/
      test_trino_integration.py   # 실 Trino, 환경변수 없으면 skip
  requirements.txt
  pytest.ini
  cache/                 # 런타임 생성, gitignore됨
```

책임 분리 원칙: 순수 로직(해시·날짜·매니페스트·사전 컷·파티션 계산·로컬 조인·수렴)과 서버 I/O(fetch/profile/cleanup의 Trino 호출)를 파일 안에서 분리하고, 서버 호출은 함수 주입으로 테스트에서 대체한다.

---

## Task 0: 프로젝트 스캐폴딩

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `data_layer/__init__.py`, `tests/conftest.py`
- Modify: `.gitignore` (이미 `cache/`, `__pycache__/`, `.venv/` 포함 — 확인만)

- [ ] **Step 1: requirements.txt 작성**

```
trino==0.336.0
duckdb>=1.1.0
pandas>=2.0.0
pyarrow>=15.0.0
pytest>=8.0.0
```

- [ ] **Step 2: venv 생성 및 설치**

Run:
```bash
cd /Users/roen.axz-pc/Desktop/projects/data_analysis
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
Expected: 설치 성공, 마지막에 `Successfully installed ...`

- [ ] **Step 3: pytest.ini 작성**

```ini
[pytest]
testpaths = tests
markers =
    integration: 실 Trino 접속이 필요한 테스트 (환경변수 없으면 skip)
```

- [ ] **Step 4: 빈 패키지 초기화 파일**

`data_layer/__init__.py`:
```python
"""정량 분석 공용 데이터 접근·캐시 레이어."""
```

- [ ] **Step 5: conftest.py (공용 fixture)**

`tests/conftest.py`:
```python
import pandas as pd
import pytest

from data_layer.config import Config


@pytest.fixture
def config(tmp_path):
    c = Config(root=tmp_path / "cache")
    c.ensure_dirs()
    return c


@pytest.fixture
def sample_events():
    # 자정을 넘는 세션(u1)과 단일 세션(u2)을 포함한 최소 이벤트 셋
    return pd.DataFrame(
        {
            "app_user_id": ["u1", "u1", "u1", "u2", "u2"],
            "isuid": ["s1", "s1", "s1", "s2", "s2"],
            "access_time": [
                "2026-01-05 23:59:50",
                "2026-01-06 00:00:10",
                "2026-01-06 00:00:30",
                "2026-01-06 09:00:00",
                "2026-01-06 09:01:00",
            ],
            "access_timestamp": [
                1767625190000,
                1767625210000,
                1767625230000,
                1767657600000,
                1767657660000,
            ],
            "day": ["2026-01-05", "2026-01-06", "2026-01-06", "2026-01-06", "2026-01-06"],
            "action_name": ["홈탭_진입", "뉴스_1슬롯", "앱종료", "홈탭_진입", "앱종료"],
        }
    )
```

- [ ] **Step 6: import 스모크 테스트**

`tests/test_util.py` (임시 placeholder — Task 1에서 채움):
```python
def test_package_imports():
    import data_layer  # noqa: F401
```

Run: `.venv/bin/pytest tests/test_util.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini data_layer/__init__.py tests/conftest.py tests/test_util.py
git commit -m "chore: scaffold data_layer package and test harness"
```

---

## Task 1: util.py — content_hash, day_strings

**Files:**
- Create: `data_layer/util.py`
- Test: `tests/test_util.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_util.py` (Task 0의 placeholder 함수는 유지):
```python
from data_layer.util import content_hash, day_strings


def test_content_hash_is_stable_and_order_independent():
    a = content_hash("q", {"x": 1, "y": 2})
    b = content_hash("q", {"y": 2, "x": 1})
    assert a == b
    assert isinstance(a, str) and len(a) == 16


def test_content_hash_changes_with_input():
    assert content_hash("q", 1) != content_hash("q", 2)


def test_day_strings_inclusive():
    assert day_strings("2026-01-05", "2026-01-07") == [
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
    ]


def test_day_strings_single_day():
    assert day_strings("2026-01-05", "2026-01-05") == ["2026-01-05"]


def test_day_strings_rejects_reversed_range():
    import pytest

    with pytest.raises(ValueError):
        day_strings("2026-01-07", "2026-01-05")
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_util.py -v`
Expected: FAIL — `ImportError: cannot import name 'content_hash'`

- [ ] **Step 3: 구현**

`data_layer/util.py`:
```python
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta


def content_hash(*parts) -> str:
    """입력의 안정적 16자 sha256. dict 키 순서에 무관."""
    blob = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def day_strings(start: str, end: str) -> list[str]:
    """[start, end] 양끝 포함 ISO 날짜 문자열 리스트."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    if e < s:
        raise ValueError(f"end {end} is before start {start}")
    out: list[str] = []
    d = s
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_util.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/util.py tests/test_util.py
git commit -m "feat: add content_hash and day_strings helpers"
```

---

## Task 2: config.py — 캐시 경로

**Files:**
- Create: `data_layer/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_config.py`:
```python
from pathlib import Path

from data_layer.config import Config


def test_config_paths(tmp_path):
    c = Config(root=tmp_path / "cache")
    assert c.events_dir == tmp_path / "cache" / "events"
    assert c.dims_dir == tmp_path / "cache" / "dims"
    assert c.results_dir == tmp_path / "cache" / "results"
    assert c.config_dir == tmp_path / "cache" / "config"
    assert c.manifest_path == tmp_path / "cache" / "manifest.json"


def test_ensure_dirs_creates_all(tmp_path):
    c = Config(root=tmp_path / "cache")
    c.ensure_dirs()
    for d in (c.events_dir, c.dims_dir, c.results_dir, c.config_dir):
        assert d.is_dir()


def test_from_env_defaults_to_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_LAYER_CACHE", raising=False)
    c = Config.from_env()
    assert c.root == Path("cache")
    monkeypatch.setenv("DATA_LAYER_CACHE", str(tmp_path / "x"))
    assert Config.from_env().root == tmp_path / "x"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.config'` (또는 이미 conftest가 import하므로 collection 에러)

- [ ] **Step 3: 구현**

`data_layer/config.py`:
```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """캐시 루트와 하위 디렉터리 경로."""

    root: Path

    @property
    def events_dir(self) -> Path:
        return self.root / "events"

    @property
    def dims_dir(self) -> Path:
        return self.root / "dims"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def ensure_dirs(self) -> None:
        for d in (self.events_dir, self.dims_dir, self.results_dir, self.config_dir):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Config":
        return cls(root=Path(os.environ.get("DATA_LAYER_CACHE", "cache")))
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/config.py tests/test_config.py
git commit -m "feat: add Config with cache paths"
```

---

## Task 3: sources.py — 소스 어댑터 정의

**Files:**
- Create: `data_layer/sources.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_sources.py`:
```python
import json

import pytest

from data_layer.sources import SourceDef, load_sources, resolve_auth


def _def(**over):
    base = dict(
        id="events",
        kind="trino",
        host="h",
        port=8443,
        catalog="cat",
        schema="sch",
        table="tbl",
        auth_ref="TIARA",
        column_map={"action_name": "action.name"},
        filters=["action.type IN ('Pageview')"],
    )
    base.update(over)
    return SourceDef(**base)


def test_version_stable_and_sensitive():
    v1 = _def().version()
    v2 = _def().version()
    assert v1 == v2
    assert _def(table="other").version() != v1


def test_load_sources_from_json(tmp_path):
    p = tmp_path / "sources.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": "events",
                    "kind": "trino",
                    "host": "h",
                    "port": 8443,
                    "catalog": "cat",
                    "schema": "sch",
                    "table": "tbl",
                    "auth_ref": "TIARA",
                    "column_map": {"action_name": "action.name"},
                    "filters": [],
                }
            ]
        )
    )
    srcs = load_sources(p)
    assert set(srcs) == {"events"}
    assert srcs["events"].catalog == "cat"


def test_resolve_auth_reads_env(monkeypatch):
    monkeypatch.setenv("TIARA_ID", "roen-axz")
    monkeypatch.setenv("TIARA_PW", "secret")
    user, pw = resolve_auth(_def())
    assert (user, pw) == ("roen-axz", "secret")


def test_resolve_auth_missing_env_raises(monkeypatch):
    monkeypatch.delenv("TIARA_ID", raising=False)
    with pytest.raises(KeyError):
        resolve_auth(_def())
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.sources'`

- [ ] **Step 3: 구현**

`data_layer/sources.py`:
```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from data_layer.util import content_hash


@dataclass
class SourceDef:
    """하나의 데이터 소스 선언. 접속·테이블·컬럼 매핑을 config로 표현."""

    id: str
    kind: str
    host: str
    port: int
    catalog: str
    schema: str
    table: str
    auth_ref: str
    column_map: dict = field(default_factory=dict)
    filters: list = field(default_factory=list)

    def version(self) -> str:
        return content_hash(
            self.id,
            self.kind,
            self.host,
            self.port,
            self.catalog,
            self.schema,
            self.table,
            self.auth_ref,
            sorted(self.column_map.items()),
            list(self.filters),
        )


def load_sources(path: Path) -> dict[str, SourceDef]:
    raw = json.loads(Path(path).read_text())
    return {d["id"]: SourceDef(**d) for d in raw}


def resolve_auth(source: SourceDef) -> tuple[str, str]:
    """auth_ref 접두어로 환경변수 `<REF>_ID`, `<REF>_PW`를 읽는다."""
    user = os.environ[f"{source.auth_ref}_ID"]
    password = os.environ[f"{source.auth_ref}_PW"]
    return user, password
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_sources.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/sources.py tests/test_sources.py
git commit -m "feat: add SourceDef registry with versioning and env auth"
```

---

## Task 4: connection.py — Trino 커넥션 어댑터

**Files:**
- Create: `data_layer/connection.py`
- Test: `tests/test_connection.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_connection.py`:
```python
from trino.auth import BasicAuthentication

from data_layer.connection import trino_connect_params
from data_layer.sources import SourceDef


def _src():
    return SourceDef(
        id="events",
        kind="trino",
        host="hadoop-rabbit-trino.onkakao.net",
        port=8443,
        catalog="hadoop_rabbit_iceberg",
        schema="axz_da",
        table="all_tiara_i",
        auth_ref="TIARA",
    )


def test_connect_params_shape():
    p = trino_connect_params(_src(), "roen-axz", "secret")
    assert p["host"] == "hadoop-rabbit-trino.onkakao.net"
    assert p["port"] == 8443
    assert p["user"] == "roen-axz"
    assert p["catalog"] == "hadoop_rabbit_iceberg"
    assert p["schema"] == "axz_da"
    assert p["http_scheme"] == "https"
    assert isinstance(p["auth"], BasicAuthentication)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_connection.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.connection'`

- [ ] **Step 3: 구현**

`data_layer/connection.py`:
```python
from __future__ import annotations

import trino
from trino.auth import BasicAuthentication

from data_layer.sources import SourceDef, resolve_auth


def trino_connect_params(source: SourceDef, user: str, password: str) -> dict:
    return dict(
        host=source.host,
        port=source.port,
        user=user,
        auth=BasicAuthentication(user, password),
        http_scheme="https",
        catalog=source.catalog,
        schema=source.schema,
    )


def connect(source: SourceDef):
    """SourceDef로부터 Trino DBAPI 커넥션을 연다 (실 접속)."""
    user, password = resolve_auth(source)
    return trino.dbapi.connect(**trino_connect_params(source, user, password))
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_connection.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/connection.py tests/test_connection.py
git commit -m "feat: add Trino connection adapter"
```

---

## Task 5: manifest.py — 캐시 색인

**Files:**
- Create: `data_layer/manifest.py`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_manifest.py`:
```python
from data_layer.manifest import Manifest


def test_new_manifest_is_empty(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    assert m.event_start_days() == set()
    assert m.has_result("abc") is False


def test_add_event_partition_and_reload(tmp_path):
    path = tmp_path / "manifest.json"
    m = Manifest.load(path)
    m.add_event_partition(
        start_day="2026-01-05",
        entities=10,
        rows=100,
        size_bytes=2048,
        source_id="events",
        source_query_hash="qh",
        sample={"method": "entity", "target": 1_000_000, "seed": 7},
        window_bounds=["2026-01-05", "2026-02-01"],
    )
    m.save()

    m2 = Manifest.load(path)
    assert m2.event_start_days() == {"2026-01-05"}
    ev = m2.data["events"][0]
    assert ev["sample"]["seed"] == 7
    assert ev["window_bounds"] == ["2026-01-05", "2026-02-01"]


def test_add_and_check_result(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    m.add_result(
        result_hash="h1",
        source_summary="transition counts",
        date_range=["2026-01-05", "2026-02-01"],
        params={"k": 5},
        config_version="cfg1",
        rows=42,
        size_bytes=512,
    )
    assert m.has_result("h1") is True
    assert m.has_result("nope") is False


def test_add_dim(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    m.add_dim(name="demographics", source_id="demo", key="app_user_id", rows=999)
    assert m.data["dims"][0]["name"] == "demographics"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.manifest'`

- [ ] **Step 3: 구현**

`data_layer/manifest.py`:
```python
from __future__ import annotations

import json
from pathlib import Path


class Manifest:
    """캐시 색인. events/dims/results/config 4개 섹션."""

    def __init__(self, path: Path, data: dict):
        self.path = Path(path)
        self.data = data

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        path = Path(path)
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = {"events": [], "dims": [], "results": [], "config": {}}
        for key in ("events", "dims", "results"):
            data.setdefault(key, [])
        data.setdefault("config", {})
        return cls(path, data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    # --- events ---
    def event_start_days(self) -> set[str]:
        return {e["start_day"] for e in self.data["events"]}

    def add_event_partition(
        self,
        start_day: str,
        entities: int,
        rows: int,
        size_bytes: int,
        source_id: str,
        source_query_hash: str,
        sample: dict,
        window_bounds: list,
    ) -> None:
        self.data["events"] = [
            e for e in self.data["events"] if e["start_day"] != start_day
        ]
        self.data["events"].append(
            {
                "start_day": start_day,
                "entities": entities,
                "rows": rows,
                "size_bytes": size_bytes,
                "source_id": source_id,
                "source_query_hash": source_query_hash,
                "sample": sample,
                "window_bounds": window_bounds,
            }
        )

    # --- results ---
    def has_result(self, result_hash: str) -> bool:
        return any(r["hash"] == result_hash for r in self.data["results"])

    def add_result(
        self,
        result_hash: str,
        source_summary: str,
        date_range: list,
        params: dict,
        config_version: str,
        rows: int,
        size_bytes: int,
    ) -> None:
        self.data["results"] = [
            r for r in self.data["results"] if r["hash"] != result_hash
        ]
        self.data["results"].append(
            {
                "hash": result_hash,
                "source_summary": source_summary,
                "date_range": date_range,
                "params": params,
                "config_version": config_version,
                "rows": rows,
                "size_bytes": size_bytes,
            }
        )

    # --- dims ---
    def add_dim(self, name: str, source_id: str, key: str, rows: int) -> None:
        self.data["dims"] = [d for d in self.data["dims"] if d["name"] != name]
        self.data["dims"].append(
            {"name": name, "source_id": source_id, "key": key, "rows": rows}
        )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_manifest.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/manifest.py tests/test_manifest.py
git commit -m "feat: add Manifest index with events/results/dims"
```

---

## Task 6: profile.py — Phase 0 사전(dictionary)

**Files:**
- Create: `data_layer/profile.py`
- Test: `tests/test_profile.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_profile.py`:
```python
import pandas as pd

from data_layer.profile import build_dictionary, compute_dictionary


def _counts():
    # 누적: A=0.5, B=0.8, C=0.95, D=1.0
    return pd.DataFrame(
        {"action_name": ["A", "B", "C", "D"], "cnt": [50, 30, 15, 5]}
    )


def test_compute_dictionary_cutoff_marks_vocabulary():
    d = compute_dictionary(_counts(), cutoff=0.8)
    # 누적 0.8 이하까지: A(0.5), B(0.8) 포함; C 포함(경계 넘는 첫 항목)
    assert "A" in d["vocabulary"]
    assert "B" in d["vocabulary"]
    assert "C" in d["vocabulary"]  # 경계를 넘기는 첫 항목까지 포함
    assert "D" not in d["vocabulary"]
    assert d["cutoff"] == 0.8


def test_compute_dictionary_maps_nonvocab_to_other():
    d = compute_dictionary(_counts(), cutoff=0.8)
    assert d["mapping"]["A"] == "A"
    assert d["mapping"]["D"] == "other"


def test_compute_dictionary_applies_rules():
    rules = {"A": "HOME"}
    d = compute_dictionary(_counts(), cutoff=1.0, mapping_rules=rules)
    assert d["mapping"]["A"] == "HOME"
    assert d["mapping"]["B"] == "B"


def test_build_dictionary_uses_injected_counts_fetcher():
    called = {}

    def fake_counts(source, window):
        called["window"] = window
        return _counts()

    d = build_dictionary(
        source=object(),
        window=("2026-01-05", "2026-02-01"),
        cutoff=0.8,
        counts_fetcher=fake_counts,
    )
    assert called["window"] == ("2026-01-05", "2026-02-01")
    assert d["cutoff"] == 0.8
    assert "vocabulary" in d
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.profile'`

- [ ] **Step 3: 구현**

`data_layer/profile.py`:
```python
from __future__ import annotations

import pandas as pd


def compute_dictionary(
    counts: pd.DataFrame,
    cutoff: float = 0.95,
    mapping_rules: dict | None = None,
) -> dict:
    """action_name 카운트로부터 사전 생성.

    counts: columns [action_name, cnt].
    cutoff: 누적 비율. 이 비율을 넘기는 첫 항목까지 vocabulary에 포함.
    mapping_rules: action_name -> state 오버라이드. 없으면 vocab은 자기 자신, 그 외 'other'.
    """
    mapping_rules = mapping_rules or {}
    df = counts.sort_values("cnt", ascending=False).reset_index(drop=True)
    total = df["cnt"].sum()
    df["cum_ratio"] = df["cnt"].cumsum() / total

    vocabulary: list[str] = []
    for _, row in df.iterrows():
        vocabulary.append(row["action_name"])
        if row["cum_ratio"] >= cutoff:
            break

    vocab_set = set(vocabulary)
    mapping: dict[str, str] = {}
    for name in df["action_name"]:
        if name in mapping_rules:
            mapping[name] = mapping_rules[name]
        elif name in vocab_set:
            mapping[name] = name
        else:
            mapping[name] = "other"

    return {"cutoff": cutoff, "vocabulary": vocabulary, "mapping": mapping}


def build_dictionary(
    source,
    window: tuple[str, str],
    cutoff: float = 0.95,
    mapping_rules: dict | None = None,
    counts_fetcher=None,
) -> dict:
    """Phase 0: 서버에서 action_name 카운트를 훑어 사전 생성.

    counts_fetcher(source, window) -> DataFrame[action_name, cnt].
    테스트에서는 가짜 fetcher를 주입한다. 실제 구현은 fetch_action_counts를 쓴다.
    """
    if counts_fetcher is None:
        counts_fetcher = fetch_action_counts
    counts = counts_fetcher(source, window)
    return compute_dictionary(counts, cutoff=cutoff, mapping_rules=mapping_rules)


def fetch_action_counts(source, window: tuple[str, str]) -> pd.DataFrame:
    """실 Trino에서 기간 내 action_name 카운트만 집계 (Phase 0, 가벼움)."""
    from data_layer.connection import connect

    start, end = window
    full_table = f"{source.catalog}.{source.schema}.{source.table}"
    sql = f"""
        SELECT action.name AS action_name, COUNT(*) AS cnt
        FROM {full_table}
        WHERE date.day BETWEEN '{start}' AND '{end}'
        GROUP BY action.name
        ORDER BY cnt DESC
    """
    conn = connect(source)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_profile.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/profile.py tests/test_profile.py
git commit -m "feat: add Phase 0 dictionary profiling (cutoff/vocabulary/mapping)"
```

---

## Task 7: fetch.py — Phase 1 이벤트 fetch & 파티션 캐시

**Files:**
- Create: `data_layer/fetch.py`
- Test: `tests/test_fetch.py`

- [ ] **Step 1: 실패하는 테스트 작성 (순수 파티션 계산)**

`tests/test_fetch.py`:
```python
import pandas as pd

from data_layer.fetch import get_events, missing_start_days, read_partitions
from data_layer.manifest import Manifest


def test_missing_start_days_returns_gap_only():
    existing = {"2026-01-05", "2026-01-06"}
    assert missing_start_days(existing, "2026-01-05", "2026-01-08") == [
        "2026-01-07",
        "2026-01-08",
    ]


def test_missing_start_days_all_present():
    existing = {"2026-01-05", "2026-01-06"}
    assert missing_start_days(existing, "2026-01-05", "2026-01-06") == []


def _partition_df(day, user):
    return pd.DataFrame(
        {
            "app_user_id": [user, user],
            "isuid": [f"{user}s", f"{user}s"],
            "access_time": [f"{day} 10:00:00", f"{day} 10:01:00"],
            "access_timestamp": [1, 2],
            "day": [day, day],
            "action_name": ["홈탭_진입", "앱종료"],
        }
    )


def test_read_partitions_unions_existing_days(config):
    # 두 파티션 파일을 직접 써 두고 범위로 읽으면 합집합
    for day, user in [("2026-01-05", "u1"), ("2026-01-06", "u2")]:
        _partition_df(day, user).to_parquet(
            config.events_dir / f"start_day={day}.parquet"
        )
    df = read_partitions(config, ["2026-01-05", "2026-01-06"])
    assert len(df) == 4
    assert set(df["app_user_id"]) == {"u1", "u2"}


def test_get_events_fetches_only_missing_and_records_sample(config):
    calls = []

    def fake_fetcher(start_day):
        calls.append(start_day)
        # u1은 2026-01-05 23:59에 시작해 자정을 넘김 → 전 행이 start_day=05 조각에
        return pd.DataFrame(
            {
                "app_user_id": ["u1", "u1"],
                "isuid": ["s1", "s1"],
                "access_time": ["2026-01-05 23:59:50", "2026-01-06 00:00:10"],
                "access_timestamp": [1, 2],
                "day": ["2026-01-05", "2026-01-06"],
                "action_name": ["홈탭_진입", "앱종료"],
            }
        )

    df = get_events(
        config,
        source_id="events",
        source_version="v1",
        start="2026-01-05",
        end="2026-01-05",
        partition_fetcher=fake_fetcher,
        sample={"method": "entity", "target": 1_000_000, "seed": 7},
    )
    assert calls == ["2026-01-05"]
    # 자정 넘는 세션이 한 조각에 온전히 담김
    assert len(df) == 2

    # 매니페스트에 sample seed 기록
    m = Manifest.load(config.manifest_path)
    assert m.event_start_days() == {"2026-01-05"}
    assert m.data["events"][0]["sample"]["seed"] == 7

    # 두 번째 호출은 캐시 히트 → fetcher 미호출
    calls.clear()
    get_events(
        config,
        source_id="events",
        source_version="v1",
        start="2026-01-05",
        end="2026-01-05",
        partition_fetcher=fake_fetcher,
        sample={"method": "entity", "target": 1_000_000, "seed": 7},
    )
    assert calls == []
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.fetch'`

- [ ] **Step 3: 구현**

`data_layer/fetch.py`:
```python
from __future__ import annotations

import duckdb
import pandas as pd

from data_layer.config import Config
from data_layer.manifest import Manifest
from data_layer.util import content_hash, day_strings


def missing_start_days(existing: set[str], start: str, end: str) -> list[str]:
    return [d for d in day_strings(start, end) if d not in existing]


def _partition_path(config: Config, start_day: str):
    return config.events_dir / f"start_day={start_day}.parquet"


def read_partitions(config: Config, days: list[str]) -> pd.DataFrame:
    paths = [str(_partition_path(config, d)) for d in days if _partition_path(config, d).exists()]
    if not paths:
        return pd.DataFrame()
    con = duckdb.connect()
    try:
        return con.execute(
            "SELECT * FROM read_parquet($paths)", {"paths": paths}
        ).df()
    finally:
        con.close()


def get_events(
    config: Config,
    source_id: str,
    source_version: str,
    start: str,
    end: str,
    partition_fetcher,
    sample: dict,
    refresh: bool = False,
) -> pd.DataFrame:
    """[start, end]에 개시된 개체의 원본 이벤트를 반환. 빠진 start_day만 fetch.

    partition_fetcher(start_day) -> DataFrame: 해당 start_day에 개시된 개체를
    개체-완결 샘플로 서버에서 가져온다 (서버 I/O seam, 테스트에서 주입).
    """
    config.ensure_dirs()
    m = Manifest.load(config.manifest_path)
    existing = set() if refresh else m.event_start_days()
    to_fetch = missing_start_days(existing, start, end)

    for day in to_fetch:
        df = partition_fetcher(day)
        path = _partition_path(config, day)
        df.to_parquet(path)
        m.add_event_partition(
            start_day=day,
            entities=int(df["app_user_id"].nunique()) if len(df) else 0,
            rows=int(len(df)),
            size_bytes=int(path.stat().st_size),
            source_id=source_id,
            source_query_hash=content_hash(source_version, day, sample),
            sample=sample,
            window_bounds=[start, end],
        )
    if to_fetch:
        m.save()

    return read_partitions(config, day_strings(start, end))
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_fetch.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/fetch.py tests/test_fetch.py
git commit -m "feat: add event fetch with entity-start-day partition cache"
```

---

## Task 8: enrich.py — 차원 로컬 조인

**Files:**
- Create: `data_layer/enrich.py`
- Test: `tests/test_enrich.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_enrich.py`:
```python
import pandas as pd

from data_layer.enrich import join_dim


def test_join_dim_left_adds_attributes():
    events = pd.DataFrame(
        {"app_user_id": ["u1", "u2", "u3"], "action_name": ["a", "b", "c"]}
    )
    demo = pd.DataFrame(
        {"app_user_id": ["u1", "u2"], "gender": ["F", "M"], "age": [20, 30]}
    )
    out = join_dim(events, demo, key="app_user_id", how="left")
    out = out.sort_values("app_user_id").reset_index(drop=True)
    assert list(out["gender"]) == ["F", "M", None]
    assert len(out) == 3


def test_join_dim_preserves_event_rows():
    events = pd.DataFrame({"app_user_id": ["u1", "u1"], "x": [1, 2]})
    demo = pd.DataFrame({"app_user_id": ["u1"], "gender": ["F"]})
    out = join_dim(events, demo, key="app_user_id", how="left")
    assert len(out) == 2
    assert set(out["gender"]) == {"F"}
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_enrich.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.enrich'`

- [ ] **Step 3: 구현**

`data_layer/enrich.py`:
```python
from __future__ import annotations

import duckdb
import pandas as pd


def join_dim(
    events: pd.DataFrame,
    dim: pd.DataFrame,
    key: str = "app_user_id",
    how: str = "left",
) -> pd.DataFrame:
    """이벤트에 차원(유저 속성) 테이블을 로컬 DuckDB로 조인."""
    join_kw = {"left": "LEFT", "inner": "INNER"}[how]
    con = duckdb.connect()
    try:
        con.register("events", events)
        con.register("dim", dim)
        return con.execute(
            f"SELECT events.*, dim.* EXCLUDE ({key}) "
            f"FROM events {join_kw} JOIN dim USING ({key})"
        ).df()
    finally:
        con.close()
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_enrich.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/enrich.py tests/test_enrich.py
git commit -m "feat: add local DuckDB dimension join"
```

---

## Task 9: query.py — 로컬 실행 + 결과 해시 캐시

**Files:**
- Create: `data_layer/query.py`
- Test: `tests/test_query.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_query.py`:
```python
import pandas as pd

from data_layer.manifest import Manifest
from data_layer.query import run


def test_run_local_computes_and_caches(config):
    events = pd.DataFrame(
        {"from_state": ["A", "A", "B"], "to_state": ["B", "B", "A"]}
    )
    events.to_parquet(config.events_dir / "e.parquet")
    sql = (
        "SELECT from_state, to_state, COUNT(*) AS cnt "
        "FROM read_parquet('{p}') GROUP BY 1,2 ORDER BY 1,2"
    ).format(p=str(config.events_dir / "e.parquet"))

    df = run(config, sql, source_version="v1", config_version="c1",
             source_summary="transitions", date_range=["2026-01-05", "2026-01-06"])
    assert df.loc[df["from_state"] == "A", "cnt"].iloc[0] == 2

    # 결과 캐시 + 매니페스트 기록
    m = Manifest.load(config.manifest_path)
    assert len(m.data["results"]) == 1
    assert m.data["results"][0]["source_summary"] == "transitions"


def test_run_returns_cached_without_recompute(config, monkeypatch):
    events = pd.DataFrame({"x": [1, 2, 3]})
    events.to_parquet(config.events_dir / "e.parquet")
    sql = "SELECT SUM(x) AS s FROM read_parquet('{p}')".format(
        p=str(config.events_dir / "e.parquet")
    )
    first = run(config, sql, source_version="v1", config_version="c1")
    assert first["s"].iloc[0] == 6

    # 원본 parquet를 지워도 캐시에서 반환되어야 함
    (config.events_dir / "e.parquet").unlink()
    second = run(config, sql, source_version="v1", config_version="c1")
    assert second["s"].iloc[0] == 6


def test_refresh_recomputes(config):
    events = pd.DataFrame({"x": [1, 2, 3]})
    events.to_parquet(config.events_dir / "e.parquet")
    sql = "SELECT SUM(x) AS s FROM read_parquet('{p}')".format(
        p=str(config.events_dir / "e.parquet")
    )
    run(config, sql, source_version="v1", config_version="c1")
    # 원본을 바꾸고 refresh
    pd.DataFrame({"x": [10]}).to_parquet(config.events_dir / "e.parquet")
    out = run(config, sql, source_version="v1", config_version="c1", refresh=True)
    assert out["s"].iloc[0] == 10
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_query.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.query'`

- [ ] **Step 3: 구현**

`data_layer/query.py`:
```python
from __future__ import annotations

import duckdb
import pandas as pd

from data_layer.config import Config
from data_layer.manifest import Manifest
from data_layer.util import content_hash


def run(
    config: Config,
    sql: str,
    params: dict | None = None,
    source_version: str = "",
    config_version: str = "",
    source_summary: str = "",
    date_range: list | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """로컬 DuckDB로 sql을 실행하고 결과를 내용 해시로 캐시.

    params/source_version/config_version이 캐시 키에 들어가 무효화가 정확해진다.
    결과 DataFrame은 호출자가 만든 그대로 저장된다 (카운트+확률 등은 ②의 책임).
    """
    config.ensure_dirs()
    h = content_hash(sql, params or {}, source_version, config_version)
    path = config.results_dir / f"{h}.parquet"

    if path.exists() and not refresh:
        return pd.read_parquet(path)

    con = duckdb.connect()
    try:
        df = con.execute(sql, params or {}).df()
    finally:
        con.close()

    df.to_parquet(path)
    m = Manifest.load(config.manifest_path)
    m.add_result(
        result_hash=h,
        source_summary=source_summary,
        date_range=date_range or [],
        params=params or {},
        config_version=config_version,
        rows=int(len(df)),
        size_bytes=int(path.stat().st_size),
    )
    m.save()
    return df
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_query.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/query.py tests/test_query.py
git commit -m "feat: add local DuckDB query runner with result cache"
```

---

## Task 10: cleanup.py — 서버 임시테이블 정리

**Files:**
- Create: `data_layer/cleanup.py`
- Test: `tests/test_cleanup.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_cleanup.py`:
```python
from data_layer.cleanup import drop_temp_tables, filter_prefixed


def test_filter_prefixed():
    names = ["roen_tmp_a", "roen_tmp_b", "other", "roen_keep"]
    assert filter_prefixed(names, "roen_tmp_") == ["roen_tmp_a", "roen_tmp_b"]


def test_drop_temp_tables_issues_drops_via_fake_conn():
    executed = []

    class FakeCursor:
        def execute(self, sql):
            executed.append(sql)
            self._rows = [("roen_tmp_a",), ("roen_tmp_b",), ("keep",)]

        def fetchall(self):
            return self._rows

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    dropped = drop_temp_tables(
        FakeConn(), catalog="cat", schema="sch", prefix="roen_tmp_"
    )
    assert dropped == ["roen_tmp_a", "roen_tmp_b"]
    # 각 대상에 DROP 발행
    assert any("DROP TABLE" in s and "roen_tmp_a" in s for s in executed)
    assert not any("keep" in s and "DROP" in s for s in executed)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_cleanup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.cleanup'`

- [ ] **Step 3: 구현**

`data_layer/cleanup.py`:
```python
from __future__ import annotations


def filter_prefixed(names: list[str], prefix: str) -> list[str]:
    return [n for n in names if n.startswith(prefix)]


def drop_temp_tables(conn, catalog: str, schema: str, prefix: str) -> list[str]:
    """`prefix`로 시작하는 서버 임시 테이블을 모두 DROP. 정리된 이름 리스트 반환."""
    cur = conn.cursor()
    cur.execute(f"SHOW TABLES FROM {catalog}.{schema}")
    names = [r[0] for r in cur.fetchall()]
    targets = filter_prefixed(names, prefix)
    for name in targets:
        cur.execute(f"DROP TABLE IF EXISTS {catalog}.{schema}.{name}")
    return targets
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_cleanup.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/cleanup.py tests/test_cleanup.py
git commit -m "feat: add server temp-table sweep cleanup"
```

---

## Task 11: convergence.py — 표본 수렴 체크

**Files:**
- Create: `data_layer/convergence.py`
- Test: `tests/test_convergence.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_convergence.py`:
```python
from data_layer.convergence import check_convergence


def test_stable_metric_reports_stable():
    # 지표가 크기와 무관하게 거의 일정 → 안정
    def analysis_fn(size):
        return {"p_home_to_news": 0.50 + 0.001 * (size == 5)}

    report = check_convergence(analysis_fn, sizes=[1, 5, 10], tol=0.05)
    assert report["stable"] is True
    assert len(report["results"]) == 3


def test_unstable_metric_reports_unstable():
    # 크기에 따라 크게 변함 → 불안정
    def analysis_fn(size):
        return {"m": float(size)}

    report = check_convergence(analysis_fn, sizes=[1, 10, 100], tol=0.05)
    assert report["stable"] is False
    assert report["max_change"] > 0.05
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_convergence.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data_layer.convergence'`

- [ ] **Step 3: 구현**

`data_layer/convergence.py`:
```python
from __future__ import annotations


def check_convergence(analysis_fn, sizes: list, tol: float = 0.05) -> dict:
    """표본 크기를 키우며 핵심 지표가 안정되는지 확인.

    analysis_fn(size) -> dict[str, float]. 연속한 크기 사이의 상대 변화 최대값이
    tol 이하이면 stable=True.
    """
    results = [{"size": s, "metrics": analysis_fn(s)} for s in sizes]

    max_change = 0.0
    for prev, cur in zip(results, results[1:]):
        for key, cur_val in cur["metrics"].items():
            prev_val = prev["metrics"].get(key)
            if prev_val in (None, 0):
                continue
            change = abs(cur_val - prev_val) / abs(prev_val)
            max_change = max(max_change, change)

    return {"results": results, "max_change": max_change, "stable": max_change <= tol}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_convergence.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add data_layer/convergence.py tests/test_convergence.py
git commit -m "feat: add sample-size convergence check"
```

---

## Task 12: 공개 API + 실 Trino 통합 스모크 테스트

**Files:**
- Modify: `data_layer/__init__.py`
- Create: `tests/integration/test_trino_integration.py`, `tests/integration/__init__.py`

- [ ] **Step 1: 공개 API 재노출**

`data_layer/__init__.py`:
```python
"""정량 분석 공용 데이터 접근·캐시 레이어."""

from data_layer.config import Config
from data_layer.connection import connect
from data_layer.enrich import join_dim
from data_layer.fetch import get_events
from data_layer.manifest import Manifest
from data_layer.profile import build_dictionary, compute_dictionary
from data_layer.query import run
from data_layer.sources import SourceDef, load_sources
from data_layer.cleanup import drop_temp_tables
from data_layer.convergence import check_convergence

__all__ = [
    "Config",
    "connect",
    "join_dim",
    "get_events",
    "Manifest",
    "build_dictionary",
    "compute_dictionary",
    "run",
    "SourceDef",
    "load_sources",
    "drop_temp_tables",
    "check_convergence",
]
```

- [ ] **Step 2: __init__ import 테스트 갱신**

`tests/test_util.py`의 `test_package_imports`를 아래로 교체:
```python
def test_package_exports():
    import data_layer

    for name in ("Config", "get_events", "run", "SourceDef", "build_dictionary"):
        assert hasattr(data_layer, name)
```

Run: `.venv/bin/pytest tests/test_util.py -v`
Expected: PASS

- [ ] **Step 3: 통합 테스트 작성 (환경변수 없으면 skip)**

`tests/integration/__init__.py`: (빈 파일)

`tests/integration/test_trino_integration.py`:
```python
import os

import pytest

from data_layer.connection import connect
from data_layer.sources import SourceDef

pytestmark = pytest.mark.integration

EVENTS_SOURCE = SourceDef(
    id="events",
    kind="trino",
    host="hadoop-rabbit-trino.onkakao.net",
    port=8443,
    catalog="hadoop_rabbit_iceberg",
    schema="axz_da",
    table="all_tiara_i",
    auth_ref="TIARA",
)


@pytest.fixture(autouse=True)
def _require_creds():
    if not (os.environ.get("TIARA_ID") and os.environ.get("TIARA_PW")):
        pytest.skip("TIARA_ID/TIARA_PW not set — skipping live Trino test")


def test_connect_and_trivial_query():
    conn = connect(EVENTS_SOURCE)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_show_tables_accessible():
    conn = connect(EVENTS_SOURCE)
    try:
        cur = conn.cursor()
        cur.execute("SHOW TABLES FROM hadoop_rabbit_iceberg.axz_da")
        rows = cur.fetchall()
        assert isinstance(rows, list)
    finally:
        conn.close()
```

- [ ] **Step 4: 오프라인 전체 스위트 실행 (통합 제외)**

Run: `.venv/bin/pytest -m "not integration" -v`
Expected: 모든 유닛 테스트 PASS

- [ ] **Step 5: 통합 테스트 실행 (자격증명 있을 때)**

Run:
```bash
TIARA_ID=roen-axz TIARA_PW='<PW>' .venv/bin/pytest -m integration -v
```
Expected: PASS (자격증명 없으면 SKIPPED)

주의: PW를 셸 히스토리/저장소에 남기지 않는다. 값은 사용자가 직접 환경에 주입한다.

- [ ] **Step 6: Commit**

```bash
git add data_layer/__init__.py tests/test_util.py tests/integration/
git commit -m "feat: expose public API and add gated Trino integration tests"
```

---

## 남은 통합 작업 노트 (구현 중 참고)

- **Phase 1 서버 fetcher 실제 구현**: `get_events`의 `partition_fetcher`로 넘길 실제 함수는 별도로 작성한다 — 세션 프리픽스 임시테이블에 "해당 start_day에 개시된 개체를 개체-완결 샘플(시드 고정)"로 넣고 pull한 뒤 `drop_temp_tables`로 정리. 이 함수는 `SourceDef.filters`/`column_map`을 적용한다. 통합 테스트로 검증하며, 순수 캐시 로직(Task 7)과 분리돼 있어 오프라인 테스트가 깨지지 않는다.
- **config 아티팩트 로딩**: `sources.json`/`dictionary.vN.json` 예시 파일은 실제 소스 확정 후 `cache/config/`에 둔다(레포에 자격증명 없이). `Config`는 경로만 알고, 내용 로딩은 `load_sources`/사전 로더가 담당.
- **markov 마이그레이션**: 이 레이어가 서면 markov 노트북의 Phase 2 계산(상태매핑·전이·markov)을 서브프로젝트 ②에서 이 API 위에 얹는다. 본 계획 범위 밖.

---

## Self-Review (작성자 체크 결과)

- **Spec coverage**: 관통 원칙(원본 캐시+config) → Task 6/7/9의 config·source_version 키. 하이브리드 연산 → query `target=local`/서버 fetcher seam. 서버 잔여물 0 → Task 10 + fetcher 노트. 내용 기반 캐시 무효화 → Task 9 해시 키(소스·config 버전 포함). 개체-start-day 파티션 → Task 7. Phase 0 사전 → Task 6. 세션-완결 샘플+시드 기록 → Task 7 manifest.sample. 세션화=config → 캐시에 굽지 않음(Phase 2, ② 범위)로 명시. 검열 → manifest window_bounds. 소스 어댑터 → Task 3/4 + `__init__`. 차원 조인 → Task 8. 카운트 저장 → query가 df 그대로 저장(호출자 책임 명시). 매니페스트 공용 → Task 5. 수렴 체크 → Task 11. 인증 env 로드 → Task 3 resolve_auth. 커버 확인됨.
- **Placeholder scan**: 코드 스텝에 실제 코드/명령/기대출력 모두 포함. "적절한 에러처리" 류 문구 없음. Task 0 conftest의 오타 방지 노트는 교체 코드까지 제시.
- **Type consistency**: `get_events(config, source_id, source_version, start, end, partition_fetcher, sample, refresh)` — 테스트/구현 시그니처 일치. `Manifest.add_event_partition/add_result/add_dim` 인자 이름 테스트와 일치. `run(...)` 키워드 인자 테스트와 일치. `compute_dictionary`/`build_dictionary` 반환 dict 키(`cutoff/vocabulary/mapping`) 일관.

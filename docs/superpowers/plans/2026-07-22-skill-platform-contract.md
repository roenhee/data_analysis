# 스킬↔플랫폼 경계 계약 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ②(스킬)가 생산하고 ③(플랫폼)이 소비하는 공유 계약 코드를 `data_layer`에 구현한다 — `publish_result`/`list_results`/`read_result` + 매니페스트 확장 + config_version + 스킬 레지스트리.

**Architecture:** 결과 하나 = `<id>.parquet`(데이터) + `<id>.json`(봉투). 매니페스트에 `published[]` 색인 섹션 신설(query.run의 `results[]`와 분리해 기존 캐시 프리미티브를 안 건드림). 계약 API는 `data_layer/results.py` 하나로 진입. 전부 오프라인 테스트 가능(파일 IO만).

**Tech Stack:** Python 3.14, pandas, pyarrow(parquet), pytest. (Trino/DuckDB 불필요.)

**참고 스펙:** `docs/superpowers/specs/2026-07-22-skill-platform-contract-design.md`

---

## File Structure
```
data_layer/
  manifest.py           # 확장: published[] 섹션 + add_published/list_published/set_config
  config_artifacts.py   # 확장: config_version(dictionary, sessionization)
  results.py            # 신규: publish_result / list_results / read_result
  skills_registry.py    # 신규: register_skill / load_skills_registry
  __init__.py           # 신규 API 재노출
tests/
  test_manifest.py          # published/set_config 테스트 추가
  test_config_version.py    # 신규
  test_results.py           # 신규
  test_skills_registry.py   # 신규
```

---

## Task C1: Manifest에 published[] 색인 + set_config

**Files:**
- Modify: `data_layer/manifest.py`
- Test: `tests/test_manifest.py` (기존 테스트 유지, 아래 추가)

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_manifest.py` 끝에 append:
```python
def test_published_add_list_and_dedup(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    m.add_published(
        id="r1", run_id="run1", skill="markov", analysis_type="transition_matrix",
        title="전이 히트맵", created_at="2026-07-22T00:00:00Z", config_version="cfg1",
        data_ref="r1.parquet", envelope_ref="r1.json",
    )
    m.add_published(
        id="r2", run_id="run1", skill="markov", analysis_type="stationary_dist",
        title="정상분포", created_at="2026-07-22T00:00:01Z", config_version="cfg1",
        data_ref="r2.parquet", envelope_ref="r2.json",
    )
    m.add_published(
        id="r3", run_id="run2", skill="markov", analysis_type="exit_prob",
        title="이탈확률", created_at="2026-07-22T00:00:02Z", config_version="cfg1",
        data_ref="r3.parquet", envelope_ref="r3.json",
    )
    assert len(m.list_published()) == 3
    assert {p["id"] for p in m.list_published(run_id="run1")} == {"r1", "r2"}

    # dedup by id (재-add는 교체)
    m.add_published(
        id="r1", run_id="run1", skill="markov", analysis_type="transition_matrix",
        title="전이 히트맵 v2", created_at="2026-07-22T00:00:03Z", config_version="cfg2",
        data_ref="r1.parquet", envelope_ref="r1.json",
    )
    hits = [p for p in m.list_published() if p["id"] == "r1"]
    assert len(hits) == 1 and hits[0]["title"] == "전이 히트맵 v2"


def test_published_survives_save_reload(tmp_path):
    path = tmp_path / "manifest.json"
    m = Manifest.load(path)
    m.add_published(
        id="r1", run_id="run1", skill="markov", analysis_type="t", title="x",
        created_at="t0", config_version="cfg1", data_ref="r1.parquet", envelope_ref="r1.json",
    )
    m.save()
    assert Manifest.load(path).list_published()[0]["id"] == "r1"


def test_set_config_populates_top_level(tmp_path):
    path = tmp_path / "manifest.json"
    m = Manifest.load(path)
    m.set_config(dictionary_version="d1", sessionization_version="s1", sources_version="src1")
    m.save()
    cfg = Manifest.load(path).data["config"]
    assert cfg == {"dictionary_version": "d1", "sessionization_version": "s1", "sources_version": "src1"}
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/test_manifest.py -v` → 새 3개 실패(AttributeError: add_published/list_published/set_config).

- [ ] **Step 3: 구현** — `data_layer/manifest.py` 수정. `load()`의 setdefault 루프에 `published`도 추가하고, 클래스에 메서드 3개 추가.

`load()`에서 백필 키 목록을 확장 (기존):
```python
        for key in ("events", "dims", "results"):
            data.setdefault(key, [])
```
을 아래로:
```python
        for key in ("events", "dims", "results", "published"):
            data.setdefault(key, [])
```

클래스에 메서드 추가 (dims 섹션 아래, 파일 끝):
```python
    # --- published (스킬↔플랫폼 결과 색인) ---
    def add_published(
        self,
        id: str,
        run_id: str,
        skill: str,
        analysis_type: str,
        title: str,
        created_at: str,
        config_version: str,
        data_ref: str,
        envelope_ref: str,
    ) -> None:
        self.data["published"] = [
            p for p in self.data["published"] if p["id"] != id
        ]
        self.data["published"].append(
            {
                "id": id,
                "run_id": run_id,
                "skill": skill,
                "analysis_type": analysis_type,
                "title": title,
                "created_at": created_at,
                "config_version": config_version,
                "data_ref": data_ref,
                "envelope_ref": envelope_ref,
            }
        )

    def list_published(self, run_id: str | None = None) -> list:
        pubs = self.data["published"]
        if run_id is not None:
            return [p for p in pubs if p["run_id"] == run_id]
        return list(pubs)

    # --- top-level config 버전 ---
    def set_config(
        self,
        dictionary_version: str,
        sessionization_version: str,
        sources_version: str,
    ) -> None:
        self.data["config"] = {
            "dictionary_version": dictionary_version,
            "sessionization_version": sessionization_version,
            "sources_version": sources_version,
        }
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest tests/test_manifest.py -v` (기존+새 테스트 전부 pass). 전체 `.venv/bin/pytest -m "not integration" -q` green.

- [ ] **Step 5: Commit**
```bash
git add data_layer/manifest.py tests/test_manifest.py
git commit -m "feat: add manifest published[] index and set_config"
```

---

## Task C2: config_version 헬퍼

**Files:**
- Modify: `data_layer/config_artifacts.py`
- Test: `tests/test_config_version.py`

- [ ] **Step 1: 실패 테스트** — `tests/test_config_version.py`:
```python
from data_layer.config_artifacts import config_version


def test_config_version_stable_and_order_independent():
    d = {"cutoff": 0.95, "mapping": {"A": "A", "B": "other"}}
    s = {"timeout_min": 30}
    v1 = config_version(d, s)
    v2 = config_version({"mapping": {"B": "other", "A": "A"}, "cutoff": 0.95}, {"timeout_min": 30})
    assert v1 == v2
    assert isinstance(v1, str) and len(v1) == 16


def test_config_version_changes_with_dictionary_or_sessionization():
    d = {"cutoff": 0.95}
    s = {"timeout_min": 30}
    base = config_version(d, s)
    assert config_version({"cutoff": 0.90}, s) != base
    assert config_version(d, {"timeout_min": 15}) != base
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/test_config_version.py -v` → FAIL (ImportError: config_version).

- [ ] **Step 3: 구현** — `data_layer/config_artifacts.py`에 추가 (파일 상단 import에 `from data_layer.util import content_hash` 추가, 함수 추가):
```python
from data_layer.util import content_hash


def config_version(dictionary: dict, sessionization: dict) -> str:
    """사전(dictionary)+세션화 config로부터 안정적 버전 문자열.

    content_hash가 dict 키 순서에 무관하므로 같은 내용이면 같은 버전.
    사전이나 세션화가 바뀌면 버전도 바뀐다.
    """
    return content_hash(dictionary, sessionization)
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest tests/test_config_version.py -v` → 2 passed. 전체 green.

- [ ] **Step 5: Commit**
```bash
git add data_layer/config_artifacts.py tests/test_config_version.py
git commit -m "feat: add config_version helper (dictionary+sessionization)"
```

---

## Task C3: results.py — publish_result / list_results / read_result

**Files:**
- Create: `data_layer/results.py`
- Test: `tests/test_results.py`

- [ ] **Step 1: 실패 테스트** — `tests/test_results.py`:
```python
import pandas as pd

from data_layer.results import list_results, publish_result, read_result


def _data():
    return pd.DataFrame(
        {"from_state": ["A", "A", "B"], "to_state": ["B", "A", "A"], "p": [0.6, 0.4, 1.0]}
    )


def test_publish_writes_parquet_json_and_index(config):
    rid = publish_result(
        config,
        run_id="run1",
        skill="markov",
        analysis_type="transition_matrix",
        title="전이 히트맵",
        data=_data(),
        viz={"chart_type": "heatmap", "encoding": {"x": "from_state", "y": "to_state", "value": "p"}},
        params={"window": ["2026-01-05", "2026-02-01"], "seed": 7},
        config_version="cfg1",
        insight="홈탭→뉴스뷰 전이가 강함",
        created_at="2026-07-22T00:00:00Z",
    )
    assert (config.results_dir / f"{rid}.parquet").exists()
    assert (config.results_dir / f"{rid}.json").exists()

    idx = list_results(config)
    assert len(idx) == 1
    assert idx[0]["id"] == rid
    assert idx[0]["run_id"] == "run1"
    assert idx[0]["analysis_type"] == "transition_matrix"


def test_read_result_returns_data_and_envelope(config):
    rid = publish_result(
        config, run_id="run1", skill="markov", analysis_type="transition_matrix",
        title="전이 히트맵", data=_data(),
        viz={"chart_type": "heatmap", "encoding": {"x": "from_state", "y": "to_state", "value": "p"}},
        params={"seed": 7}, config_version="cfg1", insight="i", caveats="c",
        created_at="2026-07-22T00:00:00Z",
    )
    df, env = read_result(config, rid)
    assert list(df.columns) == ["from_state", "to_state", "p"]
    assert len(df) == 3
    assert env["title"] == "전이 히트맵"
    assert env["viz"]["chart_type"] == "heatmap"
    assert env["insight"] == "i"
    assert env["caveats"] == "c"
    assert env["config_version"] == "cfg1"
    # columns 메타가 데이터 컬럼을 반영
    assert [c["name"] for c in env["columns"]] == ["from_state", "to_state", "p"]


def test_list_results_filters_by_run(config):
    common = dict(
        skill="markov", data=_data(),
        viz={"chart_type": "table", "encoding": {}}, params={}, config_version="cfg1",
        created_at="t",
    )
    publish_result(config, run_id="runA", analysis_type="t1", title="a", **common)
    publish_result(config, run_id="runB", analysis_type="t2", title="b", **common)
    assert {r["run_id"] for r in list_results(config)} == {"runA", "runB"}
    assert len(list_results(config, run_id="runA")) == 1
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/test_results.py -v` → FAIL (ModuleNotFoundError: data_layer.results).

- [ ] **Step 3: 구현** — `data_layer/results.py`:
```python
from __future__ import annotations

import datetime
import json

import pandas as pd

from data_layer.config import Config
from data_layer.manifest import Manifest
from data_layer.util import content_hash


def publish_result(
    config: Config,
    run_id: str,
    skill: str,
    analysis_type: str,
    title: str,
    data: pd.DataFrame,
    viz: dict,
    params: dict,
    config_version: str,
    insight: str | None = None,
    caveats: str | None = None,
    created_at: str | None = None,
) -> str:
    """분석 산출물 하나를 계약 형식으로 발행.

    <id>.parquet(데이터) + <id>.json(봉투)을 쓰고 매니페스트 published[]에 색인.
    id는 (run_id, analysis_type, title)로 결정적. ②가 호출한다.
    """
    config.ensure_dirs()
    rid = content_hash(run_id, analysis_type, title)
    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    data_ref = f"{rid}.parquet"
    envelope_ref = f"{rid}.json"
    (config.results_dir / data_ref).parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(config.results_dir / data_ref)

    columns = [{"name": str(c), "type": str(data[c].dtype)} for c in data.columns]
    envelope = {
        "id": rid,
        "run_id": run_id,
        "skill": skill,
        "analysis_type": analysis_type,
        "title": title,
        "created_at": created_at,
        "params": params,
        "config_version": config_version,
        "data_ref": data_ref,
        "columns": columns,
        "viz": viz,
        "insight": insight,
        "caveats": caveats,
    }
    (config.results_dir / envelope_ref).write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, default=str)
    )

    m = Manifest.load(config.manifest_path)
    m.add_published(
        id=rid,
        run_id=run_id,
        skill=skill,
        analysis_type=analysis_type,
        title=title,
        created_at=created_at,
        config_version=config_version,
        data_ref=data_ref,
        envelope_ref=envelope_ref,
    )
    m.save()
    return rid


def list_results(config: Config, run_id: str | None = None) -> list:
    """발행된 결과의 색인 목록(매니페스트 published[]). ③이 호출한다."""
    return Manifest.load(config.manifest_path).list_published(run_id=run_id)


def read_result(config: Config, id: str) -> tuple[pd.DataFrame, dict]:
    """발행된 결과의 (데이터 DataFrame, 봉투 dict)를 반환. ③이 호출한다."""
    envelope = json.loads((config.results_dir / f"{id}.json").read_text())
    df = pd.read_parquet(config.results_dir / envelope["data_ref"])
    return df, envelope
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest tests/test_results.py -v` → 3 passed. 전체 green.

- [ ] **Step 5: Commit**
```bash
git add data_layer/results.py tests/test_results.py
git commit -m "feat: add results contract (publish_result/list_results/read_result)"
```

---

## Task C4: skills_registry.py — 스킬 카탈로그 (경량)

**Files:**
- Create: `data_layer/skills_registry.py`
- Test: `tests/test_skills_registry.py`

- [ ] **Step 1: 실패 테스트** — `tests/test_skills_registry.py`:
```python
from data_layer.skills_registry import load_skills_registry, register_skill


def _desc(name="markov"):
    return {
        "name": name,
        "description": "행동 로그 마르코프 분석",
        "invocation": "markov 스킬 실행 후 기간/시드 지정",
        "expected_params": {"window": "[start, end]", "seed": "int"},
    }


def test_register_and_load(config):
    register_skill(config, _desc("markov"))
    register_skill(config, _desc("funnel"))
    reg = load_skills_registry(config)
    assert {s["name"] for s in reg} == {"markov", "funnel"}


def test_register_upserts_by_name(config):
    register_skill(config, _desc("markov"))
    updated = _desc("markov")
    updated["description"] = "업데이트됨"
    register_skill(config, updated)
    reg = load_skills_registry(config)
    hits = [s for s in reg if s["name"] == "markov"]
    assert len(hits) == 1 and hits[0]["description"] == "업데이트됨"


def test_load_empty_when_absent(config):
    assert load_skills_registry(config) == []
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/test_skills_registry.py -v` → FAIL (ModuleNotFoundError).

- [ ] **Step 3: 구현** — `data_layer/skills_registry.py`:
```python
from __future__ import annotations

import json

from data_layer.config import Config


def _registry_path(config: Config):
    return config.config_dir / "skills_registry.json"


def load_skills_registry(config: Config) -> list:
    """등록된 스킬 디스크립터 목록. 없으면 빈 리스트. ③이 카탈로그로 표시."""
    path = _registry_path(config)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def register_skill(config: Config, descriptor: dict) -> None:
    """스킬 디스크립터를 name 기준 upsert. ②가 스킬을 만들 때 호출."""
    config.ensure_dirs()
    reg = load_skills_registry(config)
    reg = [s for s in reg if s.get("name") != descriptor["name"]]
    reg.append(descriptor)
    _registry_path(config).write_text(json.dumps(reg, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest tests/test_skills_registry.py -v` → 3 passed. 전체 green.

- [ ] **Step 5: Commit**
```bash
git add data_layer/skills_registry.py tests/test_skills_registry.py
git commit -m "feat: add lightweight skills registry (register/load)"
```

---

## Task C5: 공개 API 재노출 + end-to-end 왕복 테스트

**Files:**
- Modify: `data_layer/__init__.py`
- Test: `tests/test_results.py` (왕복 테스트 추가)

- [ ] **Step 1: __init__ 재노출** — `data_layer/__init__.py`의 import·`__all__`에 추가:
```python
from data_layer.config_artifacts import config_version, events_source_from_json, load_dictionary
from data_layer.results import list_results, publish_result, read_result
from data_layer.skills_registry import load_skills_registry, register_skill
```
그리고 `__all__` 리스트에 다음 문자열을 추가: `"config_version"`, `"events_source_from_json"`, `"load_dictionary"`, `"publish_result"`, `"list_results"`, `"read_result"`, `"load_skills_registry"`, `"register_skill"`.

- [ ] **Step 2: 왕복 테스트 추가** — `tests/test_results.py` 끝에 append:
```python
import data_layer


def test_public_api_roundtrip(config):
    rid = data_layer.publish_result(
        config, run_id="run1", skill="markov", analysis_type="transition_matrix",
        title="t", data=_data(),
        viz={"chart_type": "heatmap", "encoding": {"x": "from_state", "y": "to_state", "value": "p"}},
        params={"seed": 7},
        config_version=data_layer.config_version({"cutoff": 0.95}, {"timeout_min": 30}),
        created_at="t0",
    )
    listed = data_layer.list_results(config, run_id="run1")
    assert len(listed) == 1 and listed[0]["id"] == rid
    df, env = data_layer.read_result(config, rid)
    assert len(df) == 3 and env["viz"]["chart_type"] == "heatmap"
    assert len(env["config_version"]) == 16
```

- [ ] **Step 3: 통과 확인** — `.venv/bin/pytest -m "not integration" -q` → 전부 pass. `python -c "import data_layer; [getattr(data_layer,n) for n in ('publish_result','list_results','read_result','config_version','register_skill','load_skills_registry')]"` 무오류.

- [ ] **Step 4: Commit**
```bash
git add data_layer/__init__.py tests/test_results.py
git commit -m "feat: expose contract API and add end-to-end roundtrip test"
```

---

## Self-Review
- **Spec coverage:** 결과 계약(단위/봉투) → C3. 저장 레이아웃(parquet+json+매니페스트) → C1(published)+C3. 계약 API(publish/list/read) → C3+C5. config_version 정의 + 매니페스트 config → C1(set_config)+C2. 스킬 카탈로그 → C4. ①에 주는 변경(신규 results.py·매니페스트 확장) → C1/C3. `query.run` 불변 유지 → published[]를 results[]와 분리해 달성.
- **Placeholder scan:** 모든 코드 스텝에 실제 코드/명령. TBD/모호 문구 없음.
- **Type consistency:** `add_published`/`list_published`/`set_config` 시그니처가 C1 정의와 C3 호출에서 일치. `publish_result`/`list_results`/`read_result` 시그니처가 C3 정의와 C5 테스트에서 일치. `config_version(dictionary, sessionization)` C2 정의와 C5 사용 일치. envelope 필드가 스펙 스키마와 일치.

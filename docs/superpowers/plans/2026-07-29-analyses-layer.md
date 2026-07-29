# 분석 층 (`analytics/analyses/`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이름 붙은 분석 6개와 연산자 2개를 만들어, Claude 와 대시보드가 **같은 코드 경로**로
숫자를 얻게 한다. 가드는 연산자 한 곳에 모으고, 모든 발행물에 봉투를 강제한다.

**Architecture:** `metrics/`(순수 프리미티브) 위에 `analyses/` 를 얹는다. 분석은
`CubeSet`(로딩된 프레임 묶음)을 받아 `AnalysisResult`(프레임 + headline 스칼라 + 봉투)를
낸다. 연산자는 분석 **함수를 받아** 세그먼트·날짜를 갈라 여러 번 호출하고 비교한다.
그래서 연산자 하나가 분석 전부에 걸린다.

**Tech Stack:** Python 3.14, pandas, numpy, pytest. `screen_communities` 만 `networkx`.

**설계**: `docs/superpowers/specs/2026-07-29-skill-platform-shape-design.md`

> **완성도가 균일하지 않다.** Task 1·2·3·6·10 은 코드까지 적혀 있다 — 새로 짜는 것이거나
> (`base`·`compare`·`decompose`·엔트로피/PageRank) 외부 의존이 붙는 것(`communities`)이라
> 틀릴 여지가 크기 때문이다. Task 5·7·8·9 는 **무엇을 감싸고 무엇을 `headline` 로 내는지는
> 명시했지만 코드는 없다** — Task 4(`session_trend`)가 그 형태를 코드로 확정하므로 같은
> 껍데기를 반복해 적지 않는다. 실행자는 Task 4 를 먼저 끝내고 그 모양을 따른다.

---

## 이 계획이 지켜야 할 것 — 전부 2026-07-29 실측

| 실패 | 틀린 답 | 옳은 답 | 어디서 막나 |
|---|---|---|---|
| 세션 큐브 그냥 합산 | 2억 8,909만 | 3,212만 | `metrics.frame` (이미 있음) |
| `uv` 합산 | 1,642만 | 959만 | `metrics.frame` (이미 있음) |
| 체류를 `cnt` 로 나눔 | 6.67초 | 10.0초 | `metrics.descriptive` (이미 있음) |
| 버전 델타 날짜 어긋남 | +2.9% | −0.4% | **`compare` (Task 2)** |
| 배포 전 테스트 트래픽 | +2.7% | −0.4% | **`compare` (Task 2)** |
| **심슨의 역설** | **−2.1%** | **+4~6%** | **`compare` + `decompose` (Task 2·3)** |

**전부 예외를 던지지 않았다.** 그래서 각 가드마다 "가드를 빼면 틀린 숫자가 나온다" 를
mutation check 로 확인한다.

## File Structure

| 파일 | 책임 |
|---|---|
| `analytics/analyses/__init__.py` | 레지스트리 재수출 |
| `analytics/analyses/base.py` | `CubeSet`·`AnalysisResult`·`publish`·레지스트리 |
| `analytics/analyses/operators.py` | `compare`·`decompose` |
| `analytics/analyses/descriptive.py` | `session_trend`·`screen_dwell_rank` |
| `analytics/analyses/flow.py` | `screen_flow`·`reachability` |
| `analytics/analyses/quality.py` | `quality_report` |
| `analytics/analyses/communities.py` | `screen_communities` (`networkx`) |

---

### Task 1: `CubeSet`·`AnalysisResult`·발행 규약

**Files:**
- Create: `analytics/analyses/__init__.py`, `analytics/analyses/base.py`
- Create: `tests/analytics/analyses/__init__.py`, `tests/analytics/analyses/test_base.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/analyses/test_base.py`:

```python
import pandas as pd
import pytest

from analytics.analyses.base import (
    AnalysisResult,
    CubeSet,
    IncompleteEnvelopeError,
    UnknownAnalysisError,
    analysis,
    get_analysis,
    list_analyses,
    publish,
)


def _cubes() -> CubeSet:
    session = pd.DataFrame([
        {"period": "2026-07-27", "service_type": "MA", "os": "android",
         "gender": "M", "age_band": "50", "daypart": "12~17",
         "app_version": "9.5.1", "sessions": 10, "uv": 8, "pv": 40,
         "events": 100, "duration_sum": 600},
    ])
    return CubeSet(session=session, transition=None, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def test_cubeset_filters_by_date():
    two = _cubes()
    extra = two.session.copy()
    extra.loc[:, "period"] = "2026-07-28"
    two = CubeSet(session=pd.concat([two.session, extra], ignore_index=True),
                  transition=None, quality=None, state_dict_version="sd_abc",
                  services=["top"], requested_dates=["2026-07-27", "2026-07-28"],
                  present_dates=["2026-07-27", "2026-07-28"])
    got = two.filter(dates=["2026-07-27"])
    assert set(got.session["period"]) == {"2026-07-27"}
    assert got.present_dates == ["2026-07-27"]


def test_cubeset_filters_by_segment():
    got = _cubes().filter(os="android")
    assert len(got.session) == 1
    got = _cubes().filter(os="ios")
    assert got.session.empty


def test_cubeset_filter_leaves_absent_cubes_absent():
    assert _cubes().filter(os="android").transition is None


def test_a_result_carries_frame_headline_and_envelope():
    r = AnalysisResult(
        frame=pd.DataFrame({"x": [1]}),
        headline={"mean": 1.0},
        envelope={"state_dict_version": "sd_abc", "services": ["top"],
                  "requested_dates": [], "present_dates": [], "missing_dates": [],
                  "is_complete": True, "coverage": {}, "warnings": []},
    )
    assert r.headline["mean"] == 1.0


def test_publish_refuses_an_envelope_missing_coverage(config):
    r = AnalysisResult(frame=pd.DataFrame({"x": [1]}), headline={},
                       envelope={"state_dict_version": "sd_abc"})
    with pytest.raises(IncompleteEnvelopeError, match="coverage"):
        publish(config, r, run_id="r1", analysis_type="t", title="x")


def test_publish_refuses_an_envelope_missing_the_dictionary_version(config):
    r = AnalysisResult(frame=pd.DataFrame({"x": [1]}), headline={},
                       envelope={"coverage": {}, "services": [], "present_dates": [],
                                 "requested_dates": [], "missing_dates": [],
                                 "is_complete": True, "warnings": []})
    with pytest.raises(IncompleteEnvelopeError, match="state_dict_version"):
        publish(config, r, run_id="r1", analysis_type="t", title="x")


def test_publish_round_trips_the_frame(config):
    from data_layer.results import read_result
    r = AnalysisResult(
        frame=pd.DataFrame({"x": [1, 2]}), headline={"mean": 1.5},
        envelope={"state_dict_version": "sd_abc", "services": ["top"],
                  "requested_dates": ["2026-07-27"], "present_dates": ["2026-07-27"],
                  "missing_dates": [], "is_complete": True, "coverage": {"dwell": 0.57},
                  "warnings": []},
    )
    rid = publish(config, r, run_id="r1", analysis_type="t", title="x")
    df, env = read_result(config, rid)
    assert df["x"].tolist() == [1, 2]
    assert env["viz"]["headline"]["mean"] == 1.5
    assert env["caveats"] is not None


def test_publishing_the_same_thing_twice_yields_one_result(config):
    from data_layer.results import list_results
    r = AnalysisResult(
        frame=pd.DataFrame({"x": [1]}), headline={},
        envelope={"state_dict_version": "sd_abc", "services": [], "coverage": {},
                  "requested_dates": [], "present_dates": [], "missing_dates": [],
                  "is_complete": True, "warnings": []},
    )
    publish(config, r, run_id="r1", analysis_type="t", title="x")
    publish(config, r, run_id="r1", analysis_type="t", title="x")
    assert len(list_results(config, run_id="r1")) == 1


def test_the_registry_finds_a_declared_analysis():
    @analysis("dummy_for_test")
    def _dummy(cubes, **params):
        return AnalysisResult(frame=pd.DataFrame(), headline={}, envelope={})

    assert "dummy_for_test" in list_analyses()
    assert get_analysis("dummy_for_test") is _dummy


def test_an_unknown_analysis_name_is_rejected():
    with pytest.raises(UnknownAnalysisError, match="nope"):
        get_analysis("nope")
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_base.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.analyses'`

- [ ] **Step 3: 구현**

`analytics/analyses/base.py`:

```python
"""분석의 공통 타입과 발행 규약.

**숫자를 만드는 코드는 이 층뿐이다.** Claude 도 대시보드도 여기를 통과하므로 두 경로가
다른 답을 낼 수 없다. 탐색은 자유롭되 발행되지 않는다 — 발행하려면 분석으로 코드화한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from data_layer.config import Config
from data_layer.results import publish_result

# 봉투에 반드시 있어야 하는 것. 하나라도 빠지면 발행을 거부한다 —
# 커버리지 57% 짜리 체류가 전수로 읽히는 것을 막는 유일한 장치다.
REQUIRED_ENVELOPE_KEYS = (
    "state_dict_version", "services", "requested_dates", "present_dates",
    "missing_dates", "is_complete", "coverage", "warnings",
)


class IncompleteEnvelopeError(ValueError):
    """봉투 필수 항목이 빠진 채 발행하려 했다."""


class UnknownAnalysisError(KeyError):
    """레지스트리에 없는 분석 이름."""


@dataclass(frozen=True)
class CubeSet:
    """분석이 받는 큐브 묶음. 없는 큐브는 `None` 이다."""

    session: pd.DataFrame | None
    transition: pd.DataFrame | None
    quality: pd.DataFrame | None
    state_dict_version: str
    services: list[str]
    requested_dates: list[str]
    present_dates: list[str]

    def filter(self, dates: list[str] | None = None, **segment) -> "CubeSet":
        """날짜·축으로 좁힌 새 `CubeSet`. 연산자가 세그먼트를 가를 때 쓴다."""
        def cut(df):
            if df is None:
                return None
            out = df
            if dates is not None and "period" in out.columns:
                out = out[out["period"].isin(dates)]
            for col, want in segment.items():
                if col not in out.columns:
                    continue
                want_list = want if isinstance(want, (list, tuple, set)) else [want]
                out = out[out[col].isin(list(want_list))]
            return out

        return CubeSet(
            session=cut(self.session),
            transition=cut(self.transition),
            quality=cut(self.quality),
            state_dict_version=self.state_dict_version,
            services=list(self.services),
            requested_dates=list(self.requested_dates),
            present_dates=list(dates) if dates is not None else list(self.present_dates),
        )


@dataclass(frozen=True)
class AnalysisResult:
    """분석 하나의 산출물.

    `headline` 은 연산자가 델타를 낼 수 있는 **스칼라**들이다. 프레임 모양은 분석마다
    다르지만 headline 은 항상 `{이름: 수}` 라 `compare` 가 분석 종류를 안 가린다.

    `compare_key` 를 주면 연산자가 그 컬럼으로 행끼리 조인해 행별 델타도 낸다.
    """

    frame: pd.DataFrame
    headline: dict[str, float]
    envelope: dict
    compare_key: str | None = None
    viz: dict = field(default_factory=dict)


_REGISTRY: dict[str, Callable] = {}


def analysis(name: str):
    """이름 붙은 분석으로 등록한다. Claude·대시보드가 이 목록에서만 고른다."""
    def wrap(fn):
        _REGISTRY[name] = fn
        fn.analysis_name = name
        return fn
    return wrap


def list_analyses() -> list[str]:
    return sorted(_REGISTRY)


def get_analysis(name: str) -> Callable:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownAnalysisError(
            f"no analysis named {name!r}; known: {', '.join(list_analyses())}"
        ) from None


def publish(
    config: Config,
    result: AnalysisResult,
    run_id: str,
    analysis_type: str,
    title: str,
    insight: str | None = None,
) -> str:
    """봉투를 검사하고 ②↔③ 계약 형식으로 발행한다.

    같은 `(run_id, analysis_type, title)` 은 같은 id 라 덮어쓴다 — 대시보드가 같은
    세그먼트를 열 번 봐도 발행물은 하나다.
    """
    missing = [k for k in REQUIRED_ENVELOPE_KEYS if k not in result.envelope]
    if missing:
        raise IncompleteEnvelopeError(
            f"envelope is missing {', '.join(missing)}; a result without coverage and "
            "the dictionary version reads as full-population when it is not"
        )
    return publish_result(
        config=config,
        run_id=run_id,
        skill="basic-analysis",
        analysis_type=analysis_type,
        title=title,
        data=result.frame,
        viz={**result.viz, "headline": result.headline},
        params={"envelope": result.envelope},
        config_version=result.envelope["state_dict_version"],
        insight=insight,
        caveats=_caveats(result.envelope),
    )


def _caveats(envelope: dict) -> str:
    """봉투에서 사람이 읽을 주의사항을 만든다."""
    bits = [f"서비스 범위 {', '.join(envelope['services']) or '(없음)'}"]
    if not envelope.get("is_complete", True):
        bits.append(f"미빌드 날짜 {len(envelope['missing_dates'])}일")
    for name, value in sorted(envelope.get("coverage", {}).items()):
        bits.append(f"{name} 커버리지 {value:.1%}")
    if envelope.get("warnings"):
        bits.append(f"품질 경고 {len(envelope['warnings'])}건")
    return " · ".join(bits)
```

`analytics/analyses/__init__.py`:

```python
"""이름 붙은 분석과 연산자. 숫자를 만드는 유일한 층."""
from analytics.analyses.base import (
    AnalysisResult, CubeSet, analysis, get_analysis, list_analyses, publish,
)

__all__ = [
    "AnalysisResult", "CubeSet", "analysis", "get_analysis", "list_analyses",
    "publish",
]
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_base.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/analyses tests/analytics/analyses
git commit -m "feat: add the analysis result type and publication contract"
```

---

### Task 2: `compare` 연산자 — 가드가 모이는 곳

**Files:**
- Create: `analytics/analyses/operators.py`
- Create: `tests/analytics/analyses/test_compare_operator.py`

**이 태스크가 이 계획의 핵심이다.** 오늘 밟은 실패 셋(날짜 어긋남·테스트 트래픽·심슨)이
전부 여기서 막힌다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import pandas as pd
import pytest

from analytics.analyses.base import AnalysisResult, CubeSet, analysis
from analytics.analyses.operators import compare


@analysis("fake_steps")
def _fake_steps(cubes, **params):
    """전이 수로 가중한 평균 걸음 수 — 테스트용 가짜 분석."""
    t = cubes.transition
    mean = float((t["steps"] * t["cnt"]).sum() / t["cnt"].sum()) if len(t) else float("nan")
    return AnalysisResult(
        frame=t, headline={"mean_steps": mean},
        envelope={"state_dict_version": "sd_abc", "services": ["top"],
                  "requested_dates": sorted(set(t["period"])),
                  "present_dates": sorted(set(t["period"])), "missing_dates": [],
                  "is_complete": True, "coverage": {}, "warnings": []},
    )


def _cubes(rows) -> CubeSet:
    t = pd.DataFrame(
        [{"period": p, "app_version": v, "cnt": c, "steps": s} for p, v, c, s in rows]
    )
    days = sorted(set(t["period"]))
    return CubeSet(session=None, transition=t, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=days, present_dates=days)


# 실측 재현: 날짜별로는 전부 a 가 크고, 합치면 뒤집힌다.
SIMPSON = _cubes([
    ("2026-07-26", "9.5.0", 143, 10.0), ("2026-07-26", "9.5.1", 3, 10.6),
    ("2026-07-27", "9.5.0", 73, 12.0), ("2026-07-27", "9.5.1", 87, 12.5),
    ("2026-07-28", "9.5.0", 26, 13.0), ("2026-07-28", "9.5.1", 139, 13.8),
])


def test_per_day_deltas_are_returned_alongside_the_pooled_one():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert len(got.per_day) == 3
    assert set(got.per_day["period"]) == {"2026-07-26", "2026-07-27", "2026-07-28"}


def test_the_pooled_delta_can_disagree_with_every_day():
    """심슨의 역설. 실측에서 날짜별 +6.4/+4.0/+6.3 인데 합산은 -2.1% 였다.

    합산 숫자 하나만 내면 정반대로 보고하게 된다.
    """
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert (got.per_day["delta_mean_steps"] > 0).all()
    assert got.pooled["mean_steps"] < 0
    assert got.sign_disagrees is True


def test_sign_agreement_is_reported_when_they_agree():
    even = _cubes([
        ("2026-07-27", "9.5.0", 100, 10.0), ("2026-07-27", "9.5.1", 100, 11.0),
        ("2026-07-28", "9.5.0", 100, 10.0), ("2026-07-28", "9.5.1", 100, 11.0),
    ])
    got = compare(even, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert got.sign_disagrees is False


def test_weight_skew_is_reported():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert got.weight_skew > 0.5


def test_dates_used_are_recorded_with_the_reason():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert got.dates_used == ["2026-07-26", "2026-07-27", "2026-07-28"]
    assert "overlap" in got.date_reason


def test_release_dates_exclude_pre_release_traffic():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0",
                  released={"9.5.1": "2026-07-27"})
    assert got.dates_used == ["2026-07-27", "2026-07-28"]
    assert "release" in got.date_reason


def test_a_disjoint_comparison_is_refused():
    from analytics.metrics.compare import ConfoundedComparisonError
    disjoint = _cubes([
        ("2026-07-26", "9.5.0", 100, 10.0), ("2026-07-28", "9.5.1", 100, 11.0),
    ])
    with pytest.raises(ConfoundedComparisonError, match="no overlapping"):
        compare(disjoint, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")


def test_the_envelope_records_both_segments_and_the_dates():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    for key in ("state_dict_version", "coverage", "services", "present_dates"):
        assert key in got.result.envelope
    assert got.result.envelope["comparison"] == {
        "on": "app_version", "a": "9.5.1", "b": "9.5.0",
    }


def test_compare_works_on_any_registered_analysis_by_name():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert "mean_steps" in got.pooled
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_compare_operator.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.analyses.operators'`

- [ ] **Step 3: 구현**

`analytics/analyses/operators.py`:

```python
"""분석에 거는 연산자. 가드가 모이는 곳이다.

**비교는 분석 종류가 아니라 분석에 거는 연산이다.** 그래서 가드를 여기 한 번만 두면
분석 전부가 자동으로 보호된다. 분석마다 따로 넣으면 반드시 하나를 빠뜨린다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analytics.analyses.base import AnalysisResult, CubeSet, get_analysis
from analytics.metrics.compare import comparable_dates, weight_skew


@dataclass(frozen=True)
class Comparison:
    """두 세그먼트 비교의 산출물.

    **합산 델타만 보면 안 된다.** 실측에서 날짜별로는 +6.4/+4.0/+6.3% 인데 합산은
    −2.1% 였다(심슨의 역설). `per_day` 와 `sign_disagrees` 가 그걸 즉시 드러낸다.
    """

    pooled: dict[str, float]
    per_day: pd.DataFrame
    weight_skew: float
    dates_used: list[str]
    date_reason: str
    sign_disagrees: bool
    result: AnalysisResult
    # `decompose` 가 같은 분석을 층별로 다시 돌리려면 이름이 필요하다.
    analysis_name: str


def _delta(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    out = {}
    for k in a.keys() & b.keys():
        out[k] = (a[k] / b[k] - 1.0) if b[k] not in (0, None) else float("nan")
    return out


def compare(
    cubes: CubeSet,
    analysis_name: str,
    on: str,
    a: str,
    b: str,
    released: dict[str, str] | None = None,
    **params,
) -> Comparison:
    """`on` 축의 두 값을 비교한다. 어느 분석에나 걸린다.

    가드:
    - **날짜 겹침 강제** — 안 겹치면 달력을 잰다(실측 +2.9% vs −0.2%)
    - **배포일 이전 제외** — 배포 전은 테스터, 다른 모집단(+2.7% vs −0.4%)
    - **날짜별 델타를 항상 함께 낸다** — 심슨의 역설을 드러낸다
    """
    fn = get_analysis(analysis_name)
    cube = cubes.transition if cubes.transition is not None else cubes.session
    days = comparable_dates(cube, on, a, b, released=released)
    reason = "overlap of both segments"
    if released and any(released.get(v) for v in (a, b)):
        reason += " after the release cutoff"

    scoped = cubes.filter(dates=days)
    res_a = fn(scoped.filter(**{on: a}), **params)
    res_b = fn(scoped.filter(**{on: b}), **params)
    pooled = _delta(res_a.headline, res_b.headline)

    rows = []
    for day in days:
        one = scoped.filter(dates=[day])
        d = _delta(fn(one.filter(**{on: a}), **params).headline,
                   fn(one.filter(**{on: b}), **params).headline)
        rows.append({"period": day, **{f"delta_{k}": v for k, v in d.items()}})
    per_day = pd.DataFrame(rows)

    disagrees = False
    for key in pooled:
        col = per_day.get(f"delta_{key}")
        if col is None or col.isna().all():
            continue
        signs = np.sign(col.dropna())
        if len(set(signs)) == 1 and np.sign(pooled[key]) not in set(signs):
            disagrees = True

    envelope = {
        **res_a.envelope,
        "present_dates": days,
        "comparison": {"on": on, "a": a, "b": b},
    }
    return Comparison(
        pooled=pooled,
        per_day=per_day,
        weight_skew=weight_skew(cube, on, a, b, released=released),
        dates_used=days,
        date_reason=reason,
        sign_disagrees=disagrees,
        result=AnalysisResult(frame=per_day, headline=pooled, envelope=envelope),
        analysis_name=analysis_name,
    )
```

- [ ] **Step 4: 통과 확인 + mutation check**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_compare_operator.py -q`
Expected: PASS (9 tests)

그다음 결함을 되주입한다. `comparable_dates` 호출을 없애고 전체 날짜를 쓰게 하면
`test_a_disjoint_comparison_is_refused` 가 실패해야 하고, `per_day` 생성을 지우면
`test_the_pooled_delta_can_disagree_with_every_day` 가 실패해야 한다.

- [ ] **Step 5: 커밋**

```bash
git add analytics/analyses/operators.py tests/analytics/analyses/test_compare_operator.py
git commit -m "feat: add the compare operator with the guards in one place"
```

---

### Task 3: `decompose` 연산자 — 심슨의 역설을 분해한다

**Files:**
- Modify: `analytics/analyses/operators.py`
- Create: `tests/analytics/analyses/test_decompose.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import pandas as pd
import pytest

from analytics.analyses.operators import compare, decompose
from tests.analytics.analyses.test_compare_operator import SIMPSON, _cubes


def test_within_and_between_sum_to_the_pooled_delta():
    """항등식. 안 맞으면 분해가 틀린 것이다."""
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(SIMPSON, c, by=["period"], metric="mean_steps")
    assert d.within + d.between == pytest.approx(c.pooled["mean_steps"], abs=1e-9)


def test_within_is_positive_when_every_stratum_is_positive():
    """실측: 날짜별 전부 +4~6% 인데 합산은 -2.1%. within 이 실제 효과다."""
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(SIMPSON, c, by=["period"], metric="mean_steps")
    assert d.within > 0
    assert d.between < 0          # 구성 변화가 부호를 뒤집었다


def test_per_stratum_carries_both_volumes():
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(SIMPSON, c, by=["period"], metric="mean_steps")
    assert {"a_cnt", "b_cnt", "delta"} <= set(d.per_stratum.columns)


def test_composition_reports_the_axis_that_shifted():
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(SIMPSON, c, by=["period"], metric="mean_steps")
    # 실측 daypart 총변동거리 0.064, os 0.038 처럼 축별 어긋남을 낸다
    assert d.composition["period"] > 0.5


def test_a_stratum_present_on_only_one_side_is_reported_not_dropped():
    lop = _cubes([
        ("2026-07-27", "9.5.0", 100, 10.0), ("2026-07-27", "9.5.1", 100, 11.0),
        ("2026-07-28", "9.5.0", 100, 10.0),
    ])
    c = compare(lop, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(lop, c, by=["period"], metric="mean_steps")
    assert "2026-07-28" in set(d.per_stratum["period"])
    assert pd.isna(d.per_stratum.set_index("period").loc["2026-07-28", "delta"])


def test_an_unknown_metric_is_rejected():
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    with pytest.raises(KeyError, match="nope"):
        decompose(SIMPSON, c, by=["period"], metric="nope")
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_decompose.py -q`
Expected: FAIL — `ImportError: cannot import name 'decompose'`

- [ ] **Step 3: 구현 — `operators.py` 끝에 추가**

```python
@dataclass(frozen=True)
class Decomposition:
    """델타를 **층 안 변화**와 **구성 변화**로 가른다.

    `within` 이 버전 효과 추정치다. `between` 은 "두 세그먼트가 서로 다른 층에 몰려
    있어서 생긴 몫" 이고, 실측에서 이게 부호를 뒤집었다(층별 +4~6%, 합산 −2.1%).
    """

    within: float
    between: float
    per_stratum: pd.DataFrame
    composition: dict[str, float]


def decompose(
    cubes: CubeSet, comparison: Comparison, by: list[str], metric: str
) -> Decomposition:
    """비교를 층으로 갈라 `within` 과 `between` 으로 분해한다.

    `within + between == pooled_delta` 가 항상 성립한다. 안 맞으면 분해가 틀렸다.

    `within` 은 **b 쪽 층 비중으로 가중한** 층별 델타의 합이다(표준 분해). 즉
    "구성이 b 와 같았다면 델타가 얼마였겠나" 이다.
    """
    if metric not in comparison.pooled:
        raise KeyError(
            f"{metric!r} is not in the comparison headline; known: "
            f"{', '.join(sorted(comparison.pooled))}"
        )
    on = comparison.result.envelope["comparison"]["on"]
    a = comparison.result.envelope["comparison"]["a"]
    b = comparison.result.envelope["comparison"]["b"]
    fn = get_analysis(comparison.analysis_name)
    cube = cubes.transition if cubes.transition is not None else cubes.session
    scoped = cubes.filter(dates=comparison.dates_used)

    rows = []
    for keys, _ in cube.groupby(by):
        keys = keys if isinstance(keys, tuple) else (keys,)
        sel = dict(zip(by, keys))
        s = scoped.filter(**sel)
        sa, sb = s.filter(**{on: a}), s.filter(**{on: b})
        ca = float(sa.transition["cnt"].sum()) if sa.transition is not None else 0.0
        cb = float(sb.transition["cnt"].sum()) if sb.transition is not None else 0.0
        if ca <= 0 or cb <= 0:
            rows.append({**sel, "a_cnt": ca, "b_cnt": cb, "delta": np.nan})
            continue
        d = _delta(fn(sa).headline, fn(sb).headline).get(metric, np.nan)
        rows.append({**sel, "a_cnt": ca, "b_cnt": cb, "delta": d})
    per = pd.DataFrame(rows)

    usable = per.dropna(subset=["delta"])
    wb = usable["b_cnt"] / usable["b_cnt"].sum() if usable["b_cnt"].sum() > 0 else 0
    within = float((usable["delta"] * wb).sum())
    between = float(comparison.pooled[metric] - within)

    composition = {}
    for axis in by:
        ga = per.groupby(axis)["a_cnt"].sum()
        gb = per.groupby(axis)["b_cnt"].sum()
        pa = ga / ga.sum() if ga.sum() > 0 else ga
        pb = gb / gb.sum() if gb.sum() > 0 else gb
        composition[axis] = float((pa - pb).abs().sum() / 2)

    return Decomposition(within=within, between=between, per_stratum=per,
                         composition=composition)
```

`Comparison.analysis_name` 은 Task 2 에서 이미 정의돼 있으므로
`get_analysis(comparison.analysis_name)` 을 그대로 쓴다. 별도 헬퍼를 만들지 않는다.

- [ ] **Step 4: 통과 확인 + mutation check**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_decompose.py -q`
Expected: PASS (6 tests)

`within` 의 가중치를 `b_cnt` 대신 `a_cnt` 로 바꾸면 항등식 테스트가 실패해야 한다.

- [ ] **Step 5: 커밋**

```bash
git commit -m "feat: decompose a comparison into within-stratum and composition parts"
```

---

### Task 4: `session_trend`

**Files:**
- Create: `analytics/analyses/descriptive.py`
- Create: `tests/analytics/analyses/test_session_trend.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

AXES = ("period", "service_type", "os", "gender", "age_band", "daypart", "app_version")


def _session_cube() -> pd.DataFrame:
    base = dict(service_type="MA", os="android", gender="M", age_band="50",
                daypart="12~17", app_version="9.5.1")
    rows = []
    for day, sess, uv in [("2026-07-27", 100, 60), ("2026-07-28", 120, 70)]:
        rows.append({**base, "period": day, "sessions": sess, "uv": uv,
                     "pv": sess * 8, "events": sess * 30, "duration_sum": sess * 600})
        rows.append({**{k: None for k in AXES}, "period": day, "sessions": sess,
                     "uv": uv, "pv": sess * 8, "events": sess * 30,
                     "duration_sum": sess * 600})
    return pd.DataFrame(rows)


def _cubes() -> CubeSet:
    return CubeSet(session=_session_cube(), transition=None, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27", "2026-07-28"],
                   present_dates=["2026-07-27", "2026-07-28"])


def test_one_row_per_date():
    got = get_analysis("session_trend")(_cubes())
    assert len(got.frame) == 2


def test_uv_comes_from_the_rollup_row_not_a_sum():
    got = get_analysis("session_trend")(_cubes()).frame.set_index("period")
    assert int(got.loc["2026-07-27", "uv"]) == 60


def test_headline_carries_scalars_for_the_comparison_operator():
    got = get_analysis("session_trend")(_cubes())
    for k in ("sessions", "pv_per_session", "seconds_per_session"):
        assert k in got.headline


def test_day_kind_is_attached_when_a_calendar_is_given():
    got = get_analysis("session_trend")(_cubes(), holidays={"2026-07-27"})
    kinds = got.frame.set_index("period")["day_kind"]
    assert kinds["2026-07-27"] == "공휴일"


def test_without_a_calendar_no_day_kind_column_is_invented():
    # 공휴일을 모르면서 평일이라고 적으면 평균이 끌려간다(실측 584.2 vs 602.8초).
    assert "day_kind" not in get_analysis("session_trend")(_cubes()).frame.columns


def test_the_envelope_carries_coverage():
    got = get_analysis("session_trend")(_cubes())
    assert "gender_known" in got.envelope["coverage"]
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현**

`analytics/analyses/descriptive.py`:

```python
"""기술통계 분석. `metrics/` 의 프리미티브를 묶어 이름 붙인다."""
from __future__ import annotations

import pandas as pd

from analytics.analyses.base import AnalysisResult, CubeSet, analysis
from analytics.metrics.calendar import day_kind
from analytics.metrics.coverage import demography_coverage, dwell_coverage
from analytics.metrics.descriptive import SESSION_AXES, engagement, uv_pv
from analytics.metrics.frame import rollup_rows


def _envelope(cubes: CubeSet, coverage: dict) -> dict:
    return {
        "state_dict_version": cubes.state_dict_version,
        "services": list(cubes.services),
        "requested_dates": list(cubes.requested_dates),
        "present_dates": list(cubes.present_dates),
        "missing_dates": [d for d in cubes.requested_dates
                          if d not in set(cubes.present_dates)],
        "is_complete": set(cubes.requested_dates) <= set(cubes.present_dates),
        "coverage": coverage,
        "warnings": [],
    }


@analysis("session_trend")
def session_trend(cubes: CubeSet, holidays: set[str] | None = None,
                  **_) -> AnalysisResult:
    """기간별 UV·PV·세션·체류.

    `uv` 는 큐브의 롤업 행에서 읽는다 — 합산하면 실측 1.71배로 부푼다.
    `holidays` 를 주면 요일 종류를 붙인다. **주지 않으면 붙이지 않는다** — 공휴일을
    모르면서 평일로 적으면 평균이 끌려간다(실측 584.2초 vs 602.8초).
    """
    folded = tuple(a for a in SESSION_AXES if a != "period")
    rows = []
    for day in sorted(set(cubes.session["period"].dropna())):
        one = cubes.session[cubes.session["period"] == day]
        base = uv_pv(one, folded=folded).iloc[0]
        eng = engagement(one, folded=folded).iloc[0]
        row = {
            "period": day,
            "sessions": int(base["sessions"]), "uv": int(base["uv"]),
            "pv": int(base["pv"]), "events": int(base["events"]),
            "sessions_per_user": eng["sessions_per_user"],
            "pv_per_session": eng["pv_per_session"],
            "seconds_per_session": eng["seconds_per_session"],
            "dwell_definition": eng["dwell_definition"],
        }
        if holidays is not None:
            row["day_kind"] = day_kind(day, holidays)
        rows.append(row)
    frame = pd.DataFrame(rows)

    total_sessions = float(frame["sessions"].sum())
    headline = {
        "sessions": total_sessions,
        "pv_per_session": float(frame["pv"].sum() / total_sessions)
        if total_sessions else float("nan"),
        "seconds_per_session": float(frame["seconds_per_session"].mean()),
    }
    return AnalysisResult(
        frame=frame, headline=headline, compare_key="period",
        envelope=_envelope(cubes, demography_coverage(cubes.session)),
        viz={"kind": "line", "x": "period"},
    )
```

- [ ] **Step 4~5: 통과 확인 · 커밋**

```bash
git commit -m "feat: add the session_trend analysis"
```

---

### Task 5: `screen_flow` (기본 마르코프 지표)

**Files:**
- Create: `analytics/analyses/flow.py`
- Create: `tests/analytics/analyses/test_screen_flow.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_frame_has_one_row_per_screen():
def test_columns_cover_exit_stationary_and_expected_steps():
def test_headline_carries_mean_expected_steps_and_mean_exit_prob():
def test_thin_cells_are_flagged_in_the_envelope_warnings():
    """엣지 셀의 cnt 중앙값은 9고 18.9%는 1이다 — 얇은 셀 경고가 붙어야 한다."""
def test_the_envelope_carries_dwell_coverage():
def test_an_empty_transition_frame_raises_rather_than_returning_zeros():
```

- [ ] **Step 2~3: 구현**

`analytics/analyses/flow.py` — `metrics.markov` 의 `transition_matrix`·
`exit_probabilities`·`stationary_distribution`·`expected_steps_to_exit`·
`absorption_probabilities`·`pointwise_mutual_information` 을 한 프레임으로 합친다.
`headline` 은 `{"mean_expected_steps", "mean_exit_prob"}`.

- [ ] **Step 4~5: 통과 확인 · 커밋**

```bash
git commit -m "feat: add the screen_flow analysis over the markov primitives"
```

---

### Task 6: `screen_flow` 확장 — 엔트로피·k-step·PageRank

**Files:**
- Modify: `analytics/metrics/markov.py`, `analytics/analyses/flow.py`
- Create: `tests/analytics/metrics/test_markov_determinism.py`

원래 마르코프 노트북에 있었으나 지금 설계에 빠져 있던 것들이다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_a_deterministic_screen_has_zero_entropy():
    # A -> B 확률 1. entropy 0, hhi 1, top_p 1, effective_choices 1.
def test_a_uniform_screen_has_maximum_entropy():
    # A -> B,C,D 각 1/3. entropy = log(3), effective_choices = 3.
def test_effective_choices_is_exp_of_entropy():
def test_hhi_matches_the_hand_calculation():
    # A -> B 0.75, C 0.25 -> hhi = 0.625
def test_p_exit_within_one_equals_the_direct_exit_probability():
def test_p_exit_within_k_is_monotonically_non_decreasing_in_k():
def test_p_exit_within_a_large_k_approaches_one_when_exit_is_reachable():
def test_pagerank_sums_to_one():
def test_pagerank_ranks_a_hub_above_a_leaf():
def test_pagerank_differs_from_stationary_on_an_absorbing_chain():
    """노트북이 pi_cond 와 pi_pr 을 대조한 이유 — 둘은 다른 중심성이다."""
```

- [ ] **Step 2~3: 구현** — `markov.py` 에 추가

```python
def determinism(P: TransitionMatrix) -> pd.DataFrame:
    """화면별 다음 걸음의 **결정성**. 엔트로피가 낮으면 경로가 예측 가능하다."""
    # entropy, hhi, top_p, effective_choices(=exp(entropy)), out_degree, top_to


def p_exit_within(P: TransitionMatrix, k: int) -> pd.DataFrame:
    """k 걸음 안에 EXIT 에 닿을 확률. 기대 걸음 수(평균)와 달리 분포의 한 점이다."""
    # P^k 를 거듭제곱해 EXIT 열을 읽는다


def pagerank(P: TransitionMatrix, damping: float = 0.85) -> pd.DataFrame:
    """감쇠 랜덤서퍼 중심성. stationary 와 **다른 질문**에 답한다 —
    stationary 는 "실제로 얼마나 머무는가", pagerank 는 "구조적으로 얼마나 중심인가".
    """
```

- [ ] **Step 4~5: 통과 확인 · 커밋**

```bash
git commit -m "feat: add entropy, k-step exit and pagerank to the flow metrics"
```

---

### Task 7: `screen_dwell_rank`

**Files:**
- Modify: `analytics/analyses/descriptive.py`
- Create: `tests/analytics/analyses/test_screen_dwell_rank.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_divides_by_measured_visits_not_transitions():
    """dur_sum/cnt 는 커버리지만큼 축소된다 — 실측 6.67초 vs 10.0초."""
def test_coverage_travels_with_the_value():
def test_a_screen_with_no_measured_dwell_is_nan_not_zero():
def test_headline_carries_the_weighted_mean_dwell():
def test_the_envelope_warns_when_dwell_coverage_is_below_half():
    """커버리지 절반 미만이면 조건부 평균이라도 대표성이 약하다. 막지 않고 경고한다."""
```

- [ ] **Step 2~5**: `metrics.descriptive.screen_dwell` 을 감싸고 봉투에
`dwell_coverage` 를 넣는다. 커밋.

```bash
git commit -m "feat: add the screen_dwell_rank analysis"
```

---

### Task 8: `quality_report`

**Files:**
- Create: `analytics/analyses/quality.py`
- Create: `tests/analytics/analyses/test_quality_report.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_one_row_per_check_and_date():
def test_ratio_is_derived_not_stored():
def test_headline_carries_the_worst_ratio_per_check():
def test_warnings_fire_above_the_configured_threshold():
def test_exit_corroboration_is_reported_as_a_positive_number():
    """이탈 정의의 뒷받침 정도 = 1 - exit_without_appexit. 실측 89.2%."""
def test_thresholds_default_to_the_shipped_config():
```

- [ ] **Step 2~5**: `metrics.envelope.quality_warnings` 를 감싼다. 커밋.

```bash
git commit -m "feat: add the quality_report analysis"
```

---

### Task 9: `reachability`

**Files:**
- Modify: `analytics/analyses/flow.py`
- Create: `tests/analytics/analyses/test_reachability.py`

노트북의 "홈 → 뉴스뷰 도달 속도"(`speed_to_newsview_after_home`)가 이 형태였다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_direct_edge_is_reached_in_one_step_with_its_probability():
def test_two_step_path_needs_two_steps():
def test_probability_is_monotonically_non_decreasing_in_k():
def test_an_unreachable_target_stays_at_zero():
def test_the_source_state_must_exist():
def test_headline_carries_p_hit_within_the_max_k():
```

- [ ] **Step 2~5**: `P^k` 누적으로 구현. 흡수시켜 중복 계산을 막는다 — 목표 상태를
흡수 상태로 바꾼 뒤 거듭제곱해야 "k 걸음 **안에**" 가 된다. 커밋.

```bash
git commit -m "feat: add the reachability analysis for time-to-screen"
```

---

### Task 10: `screen_communities`

**Files:**
- Create: `analytics/analyses/communities.py`
- Create: `tests/analytics/analyses/test_communities.py`
- Modify: `requirements.txt` (또는 `pyproject.toml`)

**외부 의존이 붙는 유일한 분석이라 마지막이다.** `networkx` 를 추가한다.

- [ ] **Step 1: 의존 추가 확인**

Run: `.venv/bin/pip install networkx && .venv/bin/python -c "import networkx; print(networkx.__version__)"`

- [ ] **Step 2: 실패하는 테스트 작성**

```python
def test_two_disconnected_clusters_are_found_as_two_communities():
def test_a_single_clique_is_one_community():
def test_every_screen_lands_in_exactly_one_community():
def test_start_and_exit_are_excluded_from_communities():
    """START/EXIT 는 모든 화면과 이어져 군집을 뭉갠다."""
def test_the_result_is_deterministic_for_a_fixed_seed():
    """Louvain 은 무작위 초기화가 있다. 시드를 고정하지 않으면 실행마다 답이 바뀐다."""
def test_headline_carries_the_community_count_and_modularity():
```

- [ ] **Step 3~5**: `networkx.community.louvain_communities(seed=...)` 로 구현.
전이 카운트를 가중치로 쓰고, `START`/`EXIT` 를 뺀 부분그래프에 적용한다. 커밋.

```bash
git commit -m "feat: add Louvain screen communities"
```

---

### Task 11: 실데이터 검증과 스킬 갱신

**Files:**
- Create: `tests/analytics/analyses/test_analyses_on_real_cubes.py`
- Modify: `.claude/skills/basic-analysis/SKILL.md`

- [ ] **Step 1: 실데이터 테스트**

`tests/analytics/metrics/test_metrics_on_real_cubes.py` 의 스키마 기준 선택 패턴을
따른다. 큐브가 없으면 skip.

```python
def test_every_registered_analysis_runs_on_real_cubes(real_cubes):
    """레지스트리 전체를 돌린다. 새 분석이 추가되면 자동으로 포함된다."""

def test_the_known_version_comparison_still_disagrees_in_sign(real_cubes):
    """실측 회귀 그물: 9.5.1 vs 9.5.0 은 날짜별 +4~6%, 합산 음수여야 한다.

    이게 통과로 바뀌면 데이터나 분해가 바뀐 것이므로 확인이 필요하다.
    """

def test_gender_comparison_is_stable_across_days(real_cubes):
    """실측: F vs M 기대 걸음 수는 15일 내내 -11.1%~-6.6% 로 부호가 안 바뀐다."""

def test_every_published_result_carries_a_complete_envelope(config, real_cubes):
```

- [ ] **Step 2: 실행 후 수치 기록**

각 분석의 실제 출력 규모와 소요 시간을 실행 보고에 적는다.

- [ ] **Step 3: `SKILL.md` 갱신**

레시피를 `analyses/` 기준으로 바꾼다. 분석 이름 목록과 연산자 사용법, 그리고
**"Claude 는 계산하지 않는다 — 분석을 고르고 결과를 말로 해석한다"** 를 명시한다.

- [ ] **Step 4: 전체 스위트 · 커밋**

```bash
git commit -m "test: run every analysis against real cubes and update the skill"
```

---

## 이 단계에서 특히 의심할 자리

1. **연산자의 가드를 분석으로 흘리지 말 것.** 날짜 겹침 검사가 분석 하나에라도 복사되면
   반드시 갈라진다. `compare` 한 곳에만 둔다.

2. **`headline` 이 없는 분석을 만들지 말 것.** 연산자가 델타를 낼 수 없어 `compare` 가
   그 분석에만 안 걸린다.

3. **봉투를 나중에 채우려 하지 말 것.** `publish` 가 거부한다. 분석이 자기 봉투를 만든다.

4. **`decompose` 의 항등식.** `within + between == pooled` 가 깨지면 분해가 틀린 것이다.
   가중치를 어느 쪽 층 비중으로 잡느냐에 따라 값이 달라지므로 테스트로 고정한다.

5. **Louvain 의 시드.** 고정하지 않으면 실행마다 군집이 바뀌어 "발행물이 재현되지 않는다".

## 서브에이전트에게 반드시 넘길 제약

- `git reset --hard`·`git checkout <path>`·`git stash`·`git restore` 금지.
- `git add -A` 금지. 추적되지 않은 `.DS_Store` 가 있다.
- 크레덴셜을 `$()` 로 셸에 끌어내면 권한 분류기에 막힌다.
  `.venv/bin/python -c '...'` 안에서 `import env` 후 `os.environ` 에 직접 넣는다.
- **설계 노트를 믿지 말고 실행하라.** 이 프로젝트의 결함은 문자열 테스트를 100% 통과한
  상태로 존재한다. 새 가드마다 결함을 되주입하는 mutation check 로 확인한다.

---

## 완료 기록 (2026-07-29, Task 3~11)

**Task 3~11 전부 완료.** 전체 스위트 **575 passed, 4 skipped, 1 xfailed** (10.5초 —
실큐브 테스트가 9초를 쓴다). 이름 붙은 분석 6개(`session_trend`·`screen_dwell_rank`·
`screen_flow`·`reachability`·`screen_communities`·`quality_report`)와 연산자 2개
(`compare`·`decompose`)가 있고, 실큐브 15일치로 전부 돌려 발행까지 확인했다.

아래는 **계획서가 틀렸거나 부족했던 곳**이다. 계획서 본문은 당시 판단 기록으로 두고
고치지 않았으니, 다음 사람은 이 절을 먼저 읽는다.

### 계획서의 실측 주장이 재현되지 않은 것

**"9.5.1 vs 9.5.0 합산 음수" 는 재현되지 않는다.** 배포일 컷오프를 걸고 MA 로 좁힌
07-26~28 에서 측정값은 날짜별 **+9.2/+4.5/+6.8%**, 합산 **+0.71%** 다. 부호가 뒤집히는
게 아니라 구성 변화가 효과의 90%를 먹는다(`within +7.5%`, `between −6.8%`,
`weight_skew 0.58`). 교훈은 같지만 **숫자가 다르므로** 회귀 그물은
`pooled < min(per_day)/5` 로 걸었다. 이 15일치에 부호까지 뒤집히는 조합은 없다.

**성별 비교의 크기도 다르다.** 계획서 −11.1%~−6.6%, 실측 −26.1%~−21.0%. 고정한 것은
크기가 아니라 성질(15일 내내 부호 불변, `weight_skew 0.009`)이다.

### 계획서의 mutation check 가 무력했던 곳

**Task 3 의 "가중치를 `a_cnt` 로 바꾸면 항등식이 깨진다" 는 틀렸다.** `between` 이
`pooled − within` 잔차라서 `within` 이 무엇이든 항등식은 성립한다. 항등식 테스트는 계약을
기록하지만 아무것도 고정하지 못한다. 그래서 두 가중치가 **부호까지 갈리는** 큐브
(+0.098 대 −0.098)로 `test_within_uses_the_b_side_stratum_weights` 를 따로 뒀다.
**잔차로 정의된 값을 검증하는 테스트를 쓸 때 이 함정을 다시 밟기 쉽다.**

### 계획서 코드에 있던 조용한 결함

- **`session_trend` 의 `seconds_per_session`.** 계획서는 `frame[...].mean()` 즉 날짜별
  평균이었는데, 같은 headline 의 `sessions`(합)·`pv_per_session`(물량 가중)과 추정량이
  섞인다. 100세션 600초 / 900세션 100초 픽스처에서 350초 대 150초로 2.3배 갈린다.
  `duration_sum` 합 / `sessions` 합으로 바꾸고 `duration_sum` 을 프레임에 넣었다.
- **`decompose` 의 `sa.transition[...] if ... else 0.0`.** 세션 큐브에서 모든 층이
  NaN → `within=0`, `between=pooled` 가 되어 "델타 전부가 구성 변화" 라고 조용히
  보고한다. 실제로 재현해 확인했다(두 층 모두 +10%, 구성 불변인데 within 0.0/between 0.1).
  `_primary_cube` 경유로 바꾸고 볼륨 컬럼이 없으면 거부한다.
- **`decompose` 가 `params` 를 버렸다.** `pooled` 는 params 로 계산했는데 층별은 기본값
  으로 재실행한다. 항등식은 그대로 성립하므로 어떤 테스트도 못 잡는다.
  `Comparison.params` 에 보관해 넘긴다.

### 실데이터에서만 드러난 것

- **`quality_report` 봉투 2.3 MB.** 경고가 (서비스×버전×날짜×검사) 단위이고 앱 버전이
  982개라 18,973건. **원인은 물량이 아니라 비교 수준이 근거와 안 맞는 것이었다** —
  임계치의 근거는 집계된 비율(전체 22.0%, top 25.5%)인데 세션 3건짜리 버전 행에 대고
  있었다. 버전을 접은 `(검사, 서비스, 날짜)` 비율에 대도록 바꿨다: **18건·2.5 KB, 전부
  2,000만 세션 이상이 뒷받침한다.** 서비스는 접지 않는다(합치면 22.0% 라 안 걸린다).
  - 처음엔 행 단위 경고를 (검사, 서비스)로 접고 **최대 비율**을 대표값으로 냈는데,
    그러면 **항상 가장 얇은 셀이 이긴다** — 실측 18건 전부 `worst_ratio` 1.000 이었고
    진짜 신호가 그 뒤에 묻혔다. 수준을 맞추면 그 대표값 자체가 필요 없어져 삭제했다.
  - 묻혀 있던 신호 둘이 드러났다: **`search` 는 체류가 15일 내내 100% 미측정**(하루
    2,000만+ 방문, 코드베이스가 이미 아는 "search 0%"), **`top` 의 나쁜 3일 30.3~32.6%**
    (하루 2,700만+ 세션). 둘 다 회귀 그물로 고정했다.
  - 맞바꿈: 한 버전만 망가진 경우는 그 서비스의 일별 숫자에 희석된다. 최소 물량 임계치를
    발명하지 않기로 택한 결과이고, 버전 질문은 `cubes.filter(app_version=...)` 로 따로 묻는다.
- **`screen_communities` 가 15개 노드에 8.8초.** 원인은 Louvain 이 아니라 250만 행을
  행마다 그래프에 넣던 조립부. 쌍으로 묶어 0.48초.
- **그 리팩터가 군집 수를 4개에서 3개로 바꿨다.** 두 그래프는 노드·엣지·가중치가 완전히
  같다(가중치 다른 엣지 0개). **노드 삽입 순서가 Louvain 의 분할을 바꾼다 — 시드를
  고정해도.** Q는 0.395878 대 0.394087 로 사실상 무승부다. 조립을 정렬로 못 박았고,
  docstring 에 "군집 수를 사실로 읽지 말 것" 을 적었다.
- **전역 레지스트리 오염.** 연산자 테스트의 `fake_steps` 가 등록돼 "모든 분석을 실큐브로"
  테스트에 새어 든다(파일 단독 실행에서는 안 보인다). 모듈로 가른다.
- **가장 굵은 화면 쌍이 자기 루프**(`top/엠탑조회` → 자기 자신)라 `reachability` 에 그냥
  넣으면 거부당한다.

### 남은 공백 (다음 사람이 할 일)

1. ~~**`CubeSet` 로더가 없다.**~~ **완료** — `analytics/analyses/cubes.py` 의
   `load_cube_set`. 키 유도를 빌더에서 `cube_key_parts` 로 빼내 **쓰는 쪽과 읽는 쪽이
   같은 함수**를 쓴다(`sql_hash` 가 큐브마다 다르고 사전·서비스·테이블 좌표까지 들어가서
   손으로 채울 수 있는 값이 아니었다 — 그래서 이 층을 실제로 쓸 방법이 없었다).
   `present_dates` 는 요청한 큐브들의 교집합이고 프레임도 그 날짜로 자른다. 부분 빌드는
   기본 거부.
   - 여기서도 조용한 결함을 하나 만들고 잡았다: 날짜 필터를 `isin` 으로만 걸어 **날짜까지
     접은 `()` 롤업 행**(`period` NULL)을 잘라냈다. 실측 세션 큐브에서 15행이 사라졌고,
     그게 "기간 전체 `uv` 는 롤업 행에서 읽어라" 가 쓰는 행이다. 행 수를 파일과 대조해
     발견했다(214,653 대 214,668).
2. **PMI 에 이름 붙은 분석이 없다.** 쌍(from, to) 단위라 화면 한 줄 프레임에 안 들어간다.
   쌍 모양 분석(`screen_pair_affinity` 같은)이 필요하고, 얇은 셀 임계치를 어떻게 할지가
   설계 결정이다(cnt 중앙값 9, 18.9%가 1).
3. ~~**`publish` 가 분석 params 를 기록하지 않는다.**~~ **완료** — `@analysis` 가 호출
   파라미터를 기록한다(기본값 포함, 집합은 정렬). `publish` 가 `params.analysis` 로 싣고,
   **같은 제목에 다른 파라미터를 발행하면 거부**한다(id 가 제목으로만 정해져 조용히
   덮어써졌다). 집합을 그대로 기록하면 `repr` 순서가 프로세스마다 달라 같은 호출이 거짓
   충돌로 거부된다는 것도 확인해서 정규화했다.
4. **세션 큐브 분석은 세그먼트 축으로 비교할 수 없다.** `compare` 의 결함이 아니라 큐브
   모양이다 — 버전으로 자르면 `(period)` 롤업 행이 사라지고 `(period, app_version)`
   grouping set 이 없어 그 슬라이스의 `uv` 가 큐브 어디에도 없다. `NonAdditiveMeasureError`
   가 정확히 그렇게 말한다. 필요하면 빌드 시점에 grouping set 을 추가한다. (그래서
   `weight_skew` 의 `measure="cnt"` 하드코딩은 아직 도달 불가다.)
5. ~~**`quality_thresholds.json` 에 임계치가 3개뿐이다.**~~ **완료** — 7개. 규칙을
   명시하고 테스트로 강제했다: **관측 최댓값 위(드리프트 탐지기) 아니면 나쁜 무리 최솟값
   아래(상시 표시), 그 사이는 안 된다.** 사이에 두면 정상 변동의 상위 몇 일만 걸린다 —
   실제로 `session_no_screen` 0.30 이 top 의 0.1960~0.3262 안이라 15일 중 3일만 걸리고
   있었고(0.15 로 내려 매일 걸린다), 그 결함을 이 규칙을 적으면서 잡았다.
   - `screen_other_ratio` 는 **일부러 없다.** Pageview 행의 NULL 이름만 세서 39억 행에서
     정확히 0.0000 인데 고장이 아니다(`null_action_name` 은 top 14~19% 지만 그 NULL 은
     Pageview 행이 아니다). `sql.py` 가 적어 둔 대로 사전 미스를 못 보는 하한이라,
     임계치를 걸면 감시되고 있다는 잘못된 안심을 준다.
   - 실측 경고 60건: `session_no_screen` top 15일, `screen_without_dwell` search 15일,
     `page_name_ambiguous` sports·search 각 15일. 넷 다 상시 표시이고 실재하는 결함이다.
   - **`page_name_ambiguous` 는 그 자체로 봐야 한다** — search 화면 이름의 70~79%,
     sports 의 27~35% 가 여러 페이지를 가리킨다. 그 두 서비스의 화면 단위 해석은 서로
     다른 페이지를 한 이름에 섞고 있다.

---

## 인수인계 (2026-07-29, Task 3 이후를 맡는 사람에게 — 당시 기록)

### 어디까지 됐나

**Task 1·2 완료.** `analytics/analyses/base.py`(`CubeSet`·`AnalysisResult`·`publish`·레지스트리)와
`operators.py`(`compare`)가 있고 테스트 24개가 붙어 있다. 전체 스위트 491 passed.

**다음은 Task 3(`decompose`).** 계획서의 코드가 그대로 쓸 수 있다.

### Task 1·2 를 하며 계획서와 달라진 것

계획서 초안에 `get_analysis_for(comparison)` 헬퍼가 있었으나 만들지 않았다 —
`Comparison.analysis_name` 을 Task 2 의 dataclass 에 넣어서 `get_analysis(c.analysis_name)` 로
충분하다. Task 3 의 코드는 이미 그렇게 적혀 있다.

`_primary_cube()` 를 하나 더 만들었다. `compare` 가 전이 큐브를 우선 쓰되 없으면 세션 큐브를
쓰는데, 그 판단이 세 곳에 반복돼서 뺐다. 둘 다 없으면 `ValueError` 다.

### mutation check 를 할 때 주의

`tests/` 를 `sys.path` 에 넣으면 `tests/analytics/` 가 진짜 `analytics/` 패키지를 가려
`ModuleNotFoundError` 가 난다. 테스트 모듈에서 픽스처를 임포트하지 말고 스크립트 안에
다시 정의한다.

그리고 **날짜 겹침 가드는 두 경로로 걸린다** — `compare` 가 직접 부르고, `weight_skew` 가
내부에서 또 부른다. 한쪽만 무력화해서는 뮤테이션이 통과하지 않는다(의도한 건 아니지만
남겨둘 만하다). 그 가드를 테스트할 때는 단위 테스트
`test_a_disjoint_comparison_is_refused` 쪽을 믿는다.

### 실데이터로 확인하고 싶을 때

큐브는 15일치가 이미 있다. Trino 불필요:

```python
import glob, pandas as pd
t = pd.concat([pd.read_parquet(p) for p in
               glob.glob("cache/cubes/transition/*/date=*.parquet")])
```

버전 비교로 뭔가 확인하려면 **9.5.1 vs 9.5.0, `service_type == "MA"`** 를 쓴다. 심슨의
역설이 재현되는 조합이라 회귀 그물로 쓸 수 있다 — 날짜별 +4~6%, 합산 음수여야 한다.

### 이 층에서 특히 의심할 자리

1. **가드를 분석으로 흘리지 말 것.** 날짜 겹침 검사가 분석 하나에라도 복사되면 갈라진다.
2. **`headline` 없는 분석을 만들지 말 것.** 연산자가 그 분석에만 안 걸린다.
3. **`decompose` 의 항등식** `within + between == pooled` — 가중치를 어느 쪽 층 비중으로
   잡느냐에 따라 값이 달라지므로 테스트로 고정한다(계획서 Task 3 에 있다).
4. **Louvain 시드**(Task 10) — 고정하지 않으면 실행마다 군집이 바뀌어 발행물이 재현되지 않는다.

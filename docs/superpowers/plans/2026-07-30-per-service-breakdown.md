# 서비스별 분해 (A5) Implementation Plan

> **완료 (2026-07-30).** Task 1~5 전부 끝났다 — 662 passed. 아래 본문은 당시 판단
> 기록이고, **계획서가 틀렸던 곳은 "완료 기록" 절**에 모아 뒀다. 참고로 쓰는 사람은
> 그 절을 먼저 읽는다 — 특히 `service_mix` 의 성능 결함과 죽은 픽스처 이야기.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 합산 지표가 어떻게 구성됐는지 결과물이 스스로 말하게 하고, 서비스별로 같은 분석을
돌리는 것을 연산자로 만든다. 지금 감춰져 있는 **서비스 간 이동**(화면 간 전이의 49.68%)을
이름 붙은 분석으로 꺼낸다.

**Architecture:** 큐브를 다시 만들지 않는다. 전이 큐브의 화면 이름이 이미
`service_code || '/' || action_name` 이라 **접두어가 곧 `service_code`** 다. 프레임 수준 순수
함수는 `analytics/metrics/services.py` 에, 분석에 거는 연산은 `analytics/analyses/operators.py`
에 둔다(`compare`·`decompose` 와 같은 자리 — 서비스별 보기도 분석 종류가 아니라 **연산**이다).

**Tech Stack:** Python 3.14, pandas 3.0.3, numpy 2.5.1, pytest. 새 의존 없음. Trino 안 씀.

**선행 측정 (둘 다 커밋됨, 먼저 읽는다):**
- `docs/superpowers/measurements/2026-07-30-screen-namespace.md` — `common.page` 와
  `action.name` 이 서로 번역되지 않는다. search 는 화면 이름이 1개다.
- `docs/superpowers/measurements/2026-07-30-click-stream-shape.md` — 클릭의 정의는
  `click.layer1` 존재다. 슬롯 좌표 보유율이 top 8.2% 대 search 99.9%.

---

## 왜 이걸 3단계보다 먼저 하나

`screen_flow` 의 `mean_expected_steps` 는 **10.62** 인데 서비스별로 다시 계산하면
**2.77~8.08** 이다. **합산값이 여섯 서비스 전부보다 크다.** 화면 간 전이 35.4억 건 중
**49.68%(17.6억)가 서비스를 건너뛰기** 때문이다 — 그 전이는 어떤 단일 서비스 안에도 없다.

합산값이 틀린 게 아니다. "앱 전체에서 한 세션이 거치는 화면 수" 로는 맞다. 문제는 **결과물에
그 구분이 없어서** 읽는 사람이 "어떤 서비스의 세션이 이렇다" 로 받는다는 것이다. 상호정보량은
서비스별 0.022(search)~0.661(top) 로 30배 차이인데 합산 0.641 은 사실상 top 값이다.

3단계 행동층은 이 문제를 키운다 — 슬롯 좌표 보유율이 top 8.2% 대 search 99.9% 라, 합산 클릭
분포를 내면 그 30배 차이가 숫자 하나에 섞인다. 먼저 표기를 넣고 그다음에 간다.

## 시작 절차 (그대로 실행)

```bash
.venv/bin/python -m pytest tests -q
```

기대: `624 passed, 4 skipped, 1 xfailed` (약 11.6초). 다르면 **작업 전에** 원인을 찾는다.

```bash
git log --oneline -1     # 84695fc docs: measure what counts as a click ...
git status -sb           # master...origin/master, 추적 안 되는 .DS_Store 하나
```

실데이터 좌표 — **세 값이 함께 맞아야 한다**:

```python
dates = [f"2026-07-{d:02d}" for d in range(14, 29)]
services = ["top", "media", "entertain", "sports", "content_v", "search"]
state_dict_version = "sd_2ab5ec25e750dda2"
```

## 반드시 알아야 하는 함정

앞 계획서(`2026-07-30-analyses-layer-remainder.md`)의 함정 10개가 **그대로 유효하다.**
특히 `services` 목록이 캐시 키에 들어가는 것(1번), 테스트용 가짜 분석이 전역 레지스트리에
있는 것(2번), 집합을 그대로 기록하지 않는 것(6번). 여기서 새로 추가되는 것:

11. **`service_type` 은 `service_code` 가 아니다.** `service_type` 실측 값은 `MA`·`MW`·`PW`
    (모바일앱·모바일웹·PC웹)이고 축 목록(`analytics/cube/axes.py`)에 있다. `service_code` 는
    `top`·`media`·… 이고 **축이 아니다** — 품질 큐브에만 컬럼으로 있고, 전이 큐브에서는 화면
    이름 접두어에 박혀 있다. 이름이 비슷해서 섞어 쓰면 조용히 다른 것을 잰다.
12. **`service_code` 를 축으로 올리지 말 것.** 세션 44.7%가 여러 서비스에 걸쳐 있어서 세션
    큐브에서 축으로 두면 한 세션이 여러 행으로 쪼개지고 세션 수·UV 가 부푼다. 원래 "서비스는
    축이 아니라 빌드 범위" 로 정한 이유다. 게다가 `sql_hash` 가 바뀌어 15일 재빌드다.
13. **서비스별로 자르면 화면 간 전이의 절반이 사라진다.** 49.68%가 서비스를 건너뛰므로
    서비스별 합이 합산과 안 맞는 게 정상이다. **연산자가 그 비율을 함께 내야 한다** —
    안 내면 "서비스별로 다 봤다" 고 읽힌다. Task 2 의 `cross_service_share` 가 그것이다.
14. **`publish` 는 빠진 봉투 키만 검사한다**(`base.REQUIRED_ENVELOPE_KEYS`). 모르는 키는
    거부하지 않으므로 Task 3 이 `service_mix` 를 추가해도 발행이 깨지지 않는다. 반대로
    **필수 키 목록에 추가하지는 않는다** — 세션 큐브만 있는 분석은 서비스를 알 수 없다.

## File Structure

| 파일 | 이 계획서에서 하는 일 |
|---|---|
| `analytics/metrics/services.py` | **신규** — `service_of`, `service_mix`. 프레임만 받는 순수 함수 |
| `analytics/analyses/operators.py` | `per_service` 연산자 추가 (Task 2) |
| `analytics/analyses/base.py` | `envelope_for` 가 `service_mix` 를 싣는다 (Task 3) |
| `analytics/analyses/flow.py` | `cross_service_flow` 분석 추가 (Task 4) |
| `tests/analytics/metrics/test_services.py` | Task 1 |
| `tests/analytics/analyses/test_per_service.py` | Task 2 |
| `tests/analytics/analyses/test_envelope_service_mix.py` | Task 3 |
| `tests/analytics/analyses/test_cross_service_flow.py` | Task 4 |
| `tests/analytics/analyses/test_analyses_on_real_cubes.py` | Task 5 회귀 그물 |
| `.claude/skills/basic-analysis/SKILL.md` | Task 5 |

> **미검증 표시.** Task 4 의 `switch_entropy` 실측값은 **아직 아무도 본 적이 없다.** 픽스처
> 값은 손계산이라 맞지만 실큐브 값은 Task 5 에서 처음 나온다. 계획서에 숫자를 적어 두지
> 않았으니 나오는 값을 그대로 기록한다.

---

### Task 1: `service_of` · `service_mix` — 접두어에서 서비스를 되찾는다

**왜:** 전이 큐브에 `service_code` 컬럼이 없다. 화면 이름 접두어가 그것이고, 그 사실을
한 곳에만 적어 둔다. 분석마다 `split("/")` 를 흩뿌리면 `START` 처리가 갈린다.

**Files:**
- Create: `analytics/metrics/services.py`
- Create: `tests/analytics/metrics/test_services.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_services.py`:

```python
"""화면 이름 접두어에서 서비스를 되찾는다. `START`·`EXIT` 는 서비스가 없다."""
import numpy as np
import pandas as pd
import pytest

from analytics.metrics.services import service_mix, service_of


def test_the_prefix_is_the_service():
    assert service_of("top/엠탑조회") == "top"
    assert service_of("content_v/contentview") == "content_v"


def test_the_other_bucket_still_belongs_to_its_service():
    """`top/other` 는 "어느 화면인지 모른다" 지 "어느 서비스인지 모른다" 가 아니다."""
    assert service_of("top/other") == "top"


def test_start_and_exit_have_no_service():
    """둘은 화면이 아니라 세션 경계다. 서비스를 붙이면 없는 서비스가 생긴다."""
    assert service_of("START") is None
    assert service_of("EXIT") is None


def test_a_screen_name_containing_a_slash_keeps_its_service():
    """서비스 코드에는 `/` 가 없으므로 **첫** 슬래시로 자른다."""
    assert service_of("media/a/b") == "media"


def test_a_missing_state_has_no_service():
    assert service_of(None) is None
    assert service_of(np.nan) is None


def _edges() -> pd.DataFrame:
    return pd.DataFrame([
        {"from_state": "top/엠탑조회", "to_state": "top/홈탭_진입", "cnt": 600},
        {"from_state": "top/홈탭_진입", "to_state": "media/뉴스", "cnt": 200},
        {"from_state": "media/뉴스", "to_state": "EXIT", "cnt": 200},
        # START 는 화면이 아니라 비중의 분모에 들어가지 않는다.
        {"from_state": "START", "to_state": "top/엠탑조회", "cnt": 5000},
    ])


def test_the_mix_is_the_share_of_screen_originating_transitions():
    """분모는 **화면에서 출발한** 전이다. `START` 를 넣으면 세션 수가 비중을 지배한다."""
    got = service_mix(_edges())
    assert got == {"top": pytest.approx(0.8), "media": pytest.approx(0.2)}


def test_the_mix_sums_to_one():
    assert sum(service_mix(_edges()).values()) == pytest.approx(1.0)


def test_an_empty_frame_gives_an_empty_mix_rather_than_raising():
    """봉투를 만들 때 부르므로 여기서 죽으면 분석 전부가 죽는다."""
    assert service_mix(pd.DataFrame(columns=["from_state", "cnt"])) == {}


def test_a_frame_without_the_columns_gives_an_empty_mix():
    assert service_mix(pd.DataFrame({"period": ["2026-07-27"]})) == {}
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_services.py -q`
기대: 전부 `ModuleNotFoundError: No module named 'analytics.metrics.services'`

- [ ] **Step 3: 구현**

`analytics/metrics/services.py`:

```python
"""화면 상태에서 서비스를 되찾는다.

전이 큐브에는 `service_code` 컬럼이 **없다.** 화면 이름이
`service_code || '/' || action_name` 으로 만들어지므로(`analytics/cube/sql.py`) 접두어가
곧 서비스다. 그 사실을 아는 곳을 이 모듈 하나로 묶는다 — 분석마다 `split("/")` 를 흩뿌리면
`START`·`EXIT` 처리가 갈리고, 없는 서비스가 조용히 생긴다.

**`service_code` 를 축으로 올리는 것과 다르다.** 세션 44.7%가 여러 서비스에 걸쳐 있어서
축으로 두면 세션이 쪼개진다. 접두어에서 읽으면 "그 **화면**의 서비스" 라 세션을 건드리지 않는다.
"""
from __future__ import annotations

import pandas as pd

# 화면이 아닌 상태. 전이 큐브가 세션 경계를 표현하려고 넣은 것이다.
NON_SCREEN_STATES = ("START", "EXIT")


def service_of(state: object) -> str | None:
    """화면 상태의 서비스. 화면이 아니면 `None`.

    서비스 코드에는 `/` 가 없으므로 **첫** 슬래시로 자른다 — 화면 이름에 슬래시가 있어도
    서비스는 맞는다.
    """
    if state is None or pd.isna(state):
        return None
    text = str(state)
    if text in NON_SCREEN_STATES:
        return None
    service, sep, _ = text.partition("/")
    return service if sep else None


def service_mix(edges: pd.DataFrame, measure: str = "cnt") -> dict[str, float]:
    """`{서비스: 비중}`. 분모는 **화면에서 출발한** 전이다.

    `START` 를 분모에 넣으면 세션 수가 비중을 지배한다 — 방문 가중 지표가 무엇으로 구성됐는지
    말하려는 것이므로 화면 출발 전이가 맞는 분모다.

    합산 지표가 어느 서비스에 붙어 있는지 봉투가 말하게 하려고 만들었다. 실측 15일에서
    top 61.8% 대 content_v 2.1% 이고, 그 사실이 없으면 합산값이 "앱 전체" 로 읽힌다.
    """
    if "from_state" not in edges.columns or measure not in edges.columns:
        return {}
    frame = edges[["from_state", measure]].copy()
    frame["service"] = [service_of(s) for s in frame["from_state"]]
    frame = frame[frame["service"].notna()]
    total = float(frame[measure].sum())
    if total <= 0:
        return {}
    grouped = frame.groupby("service")[measure].sum()
    return {str(k): float(v / total) for k, v in grouped.items()}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_services.py -q`
기대: `9 passed`

- [ ] **Step 5: mutation check**

```bash
python3 - <<'EOF'
import pathlib, subprocess
p = pathlib.Path("analytics/metrics/services.py")
src = p.read_text()
cases = [
    ('frame = frame[frame["service"].notna()]', 'pass'),
    ('service, sep, _ = text.partition("/")', 'service, sep, _ = text.rpartition("/")'),
]
for before, after in cases:
    assert before in src, before
    try:
        p.write_text(src.replace(before, after))
        r = subprocess.run([".venv/bin/python", "-m", "pytest",
                            "tests/analytics/metrics/test_services.py", "-q"],
                           capture_output=True, text=True)
        print(f"--- {before[:40]}")
        print("\n".join(l for l in r.stdout.splitlines()
                        if l.startswith("FAILED") or " passed" in l or " failed" in l))
    finally:
        p.write_text(src)
print("복원 완료")
EOF
```

기대: 첫 번째(`START` 를 분모에서 빼지 않음)는 `test_the_mix_is_the_share_of_screen_originating_transitions`
가 실패. 두 번째(`rpartition` — 마지막 슬래시로 자름)는
`test_a_screen_name_containing_a_slash_keeps_its_service` 가 실패.

- [ ] **Step 6: 커밋**

```bash
git add analytics/metrics/services.py tests/analytics/metrics/test_services.py
git commit -m "feat: recover the service from a screen state prefix"
```

---

### Task 2: `per_service` 연산자 — 어느 분석이든 서비스별로 돌린다

**왜:** 서비스별로 보려면 지금은 접두어 트릭을 아는 사람만 할 수 있다. `compare` 처럼
**연산자**로 만들면 지금 분석 7개와 앞으로 만들 행동층 분석 4개에 전부 걸린다.

핵심 산출물은 프레임이 아니라 **`outside_range`** 다 — 합산 headline 이 서비스별 값의
[최소, 최대] 밖에 있는 키 목록이다. `compare` 의 `sign_disagrees` 와 같은 역할이고,
실측에서 `mean_expected_steps` 가 정확히 그 상태다(합산 10.62 > 최대 8.08).

**Files:**
- Modify: `analytics/analyses/operators.py`
- Create: `tests/analytics/analyses/test_per_service.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/analyses/test_per_service.py`:

```python
"""서비스별 분해. 합산이 서비스 범위 밖일 수 있다는 것이 요점이다."""
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet
from analytics.analyses.operators import per_service

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _edge(f: str, t: str, cnt: int, dur_n: int | None = None) -> dict:
    n = cnt if dur_n is None else dur_n
    return {**AXES, "from_state": f, "to_state": t, "cnt": cnt,
            "dur_sum": float(n) * 10.0, "dur_n": n}


# top 은 화면 두 개를 오가고(자기 안에서 길다), media 는 한 화면에서 바로 나간다(짧다).
# 그리고 top -> media 로 넘어가는 전이가 있어서 **합친 체인이 어느 서비스보다도 길다.**
def _cubes() -> CubeSet:
    edges = pd.DataFrame([
        _edge("START", "top/a", 100),
        _edge("top/a", "top/b", 400),
        _edge("top/b", "top/a", 300),
        _edge("top/b", "media/x", 100),
        _edge("media/x", "EXIT", 100),
    ])
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd_abc", services=["top", "media"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def test_one_row_per_service():
    got = per_service(_cubes(), "screen_flow")
    assert got.frame["service"].tolist() == ["media", "top"]


def test_the_frame_carries_each_service_volume_and_share():
    got = per_service(_cubes(), "screen_flow")
    per = got.frame.set_index("service")
    # 화면에서 **출발한** 전이: top 800(400+300+100), media 100(media/x -> EXIT)
    assert per.loc["top", "cnt"] == pytest.approx(800.0)
    assert per.loc["media", "cnt"] == pytest.approx(100.0)
    assert per.loc["top", "share"] == pytest.approx(800 / 900)
    assert per.loc["media", "share"] == pytest.approx(100 / 900)


def test_each_headline_key_becomes_a_column():
    got = per_service(_cubes(), "screen_flow")
    assert "mean_expected_steps" in got.frame.columns
    assert "mean_exit_prob" in got.frame.columns


def test_the_pooled_headline_is_reported_alongside():
    got = per_service(_cubes(), "screen_flow")
    assert set(got.pooled) == {"mean_expected_steps", "mean_exit_prob"}


def test_a_pooled_value_outside_the_service_range_is_flagged():
    """이게 이 연산자의 존재 이유다 — 실측에서 기대 화면 수 합산 10.62 > 최대 8.08 이었다."""
    got = per_service(_cubes(), "screen_flow")
    assert "mean_expected_steps" in got.outside_range
    lo, hi = got.outside_range["mean_expected_steps"]
    assert got.pooled["mean_expected_steps"] > hi


def test_the_cross_service_share_is_reported():
    """서비스별로 자르면 서비스를 건너뛰는 전이가 사라진다. 얼마나 사라졌는지 말해야 한다.

    **분모가 `share` 와 다르다.** `share` 는 화면에서 *출발한* 전이(900, `-> EXIT` 포함)
    기준이고, 이쪽은 화면에서 화면으로 간 전이(800, `-> EXIT` 제외) 기준이다 — 서비스를
    건너뛰는지 물으려면 도착도 화면이어야 한다. 두 분모를 섞으면 물량이 조용히 틀린다.
    """
    got = per_service(_cubes(), "screen_flow")
    # 화면->화면 800(400+300+100) 중 top/b -> media/x 100 건이 서비스를 건너뛴다.
    assert got.cross_service_share == pytest.approx(100 / 800)


def test_a_session_cube_analysis_is_refused_with_the_reason():
    """세션은 서비스로 못 가른다 — 44.7%가 여러 서비스에 걸쳐 있어 합이 부푼다."""
    sessions = CubeSet(session=pd.DataFrame([{**AXES, "sessions": 10, "uv": 5,
                                              "pv": 80, "events": 300,
                                              "duration_sum": 6000}]),
                       transition=None, quality=None, state_dict_version="sd_abc",
                       services=["top"], requested_dates=["2026-07-27"],
                       present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="cannot be split by service"):
        per_service(sessions, "session_trend")


def test_a_service_whose_analysis_raises_is_reported_as_nan_not_dropped():
    """한 서비스에서 분석이 죽어도 나머지는 낸다. 조용히 빠지면 표가 전수처럼 읽힌다."""
    got = per_service(_cubes(), "reachability", source="top/a", target="top/b")
    per = got.frame.set_index("service")
    assert pd.isna(per.loc["media", "p_hit_within_10"])
    assert per.loc["top", "p_hit_within_10"] > 0
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_per_service.py -q`
기대: 전부 `ImportError: cannot import name 'per_service'`

- [ ] **Step 3: 구현 — `operators.py` 끝에 추가**

상단 임포트에 추가한다:

```python
from analytics.metrics.services import service_mix, service_of
```

```python
@dataclass(frozen=True)
class ServiceBreakdown:
    """같은 분석을 서비스별로 돌린 결과.

    `outside_range` 가 이 연산자의 존재 이유다. 서비스는 축이 아니라 빌드 범위라(세션
    44.7%가 여러 서비스에 걸친다) 분석이 합산값 하나를 내는데, **그 값이 서비스별 값의
    범위 밖일 수 있다.** 실측 15일에서 `mean_expected_steps` 합산 10.62 는 최대값
    8.08 보다도 크다 — 화면 간 전이의 49.68%가 서비스를 건너뛰어서, 합친 체인에는 어떤
    단일 서비스 안에도 없는 전이가 들어 있기 때문이다.

    `cross_service_share` 는 서비스별로 자를 때 **사라진** 전이 비중이다. 안 내면
    "서비스별로 다 봤다" 고 읽힌다.
    """

    frame: pd.DataFrame
    pooled: dict[str, float]
    outside_range: dict[str, tuple[float, float]]
    cross_service_share: float
    services: list[str]


def _service_slice(cubes: CubeSet, service: str) -> CubeSet:
    """그 서비스 안에서만 일어난 전이. 세션 경계(`START`·`EXIT`)는 남긴다."""
    edges = cubes.transition

    def belongs(column):
        return (edges[column].map(service_of) == service) | edges[column].isin(
            NON_SCREEN_STATES
        )

    return CubeSet(
        session=None, transition=edges[belongs("from_state") & belongs("to_state")],
        quality=cubes.quality[cubes.quality["service_code"] == service]
        if cubes.quality is not None and "service_code" in cubes.quality.columns
        else None,
        state_dict_version=cubes.state_dict_version, services=[service],
        requested_dates=list(cubes.requested_dates),
        present_dates=list(cubes.present_dates),
    )


def per_service(cubes: CubeSet, analysis_name: str, **params) -> ServiceBreakdown:
    """`analysis_name` 을 서비스별로 돌린다. 어느 분석에나 걸린다.

    서비스는 화면 이름 접두어에서 읽는다 — 큐브를 다시 만들지 않는다(`metrics/services.py`).
    한 서비스에서 분석이 죽으면 그 행을 NaN 으로 낸다. 조용히 빼면 표가 전수처럼 읽힌다.
    """
    fn = get_analysis(analysis_name)
    if cubes.transition is None:
        raise ValueError(
            f"{analysis_name!r} runs on a cube that cannot be split by service: the "
            "session cube has no service column and 44.7% of sessions span more than "
            "one service, so splitting them would double-count"
        )
    edges = cubes.transition.copy()
    edges["_from_svc"] = edges["from_state"].map(service_of)
    edges["_to_svc"] = edges["to_state"].map(service_of)

    # **분모가 둘이다. 섞으면 물량이 조용히 틀린다.**
    #  - `share`/`cnt` 는 화면에서 **출발한** 전이 기준 (`-> EXIT` 포함). 방문 가중 지표가
    #    무엇으로 구성됐는지 말하는 값이라 화면 출발이 맞는 분모다.
    #  - `cross_service_share` 는 화면에서 **화면으로** 간 전이 기준. 서비스를 건너뛰는지
    #    물으려면 도착도 화면이어야 한다.
    originating = edges[edges["_from_svc"].notna()]
    by_service = originating.groupby("_from_svc")["cnt"].sum()
    origin_total = float(by_service.sum())

    screen_to_screen = edges[edges["_from_svc"].notna() & edges["_to_svc"].notna()]
    s2s_total = float(screen_to_screen["cnt"].sum())
    crossing = float(
        screen_to_screen[
            screen_to_screen["_from_svc"] != screen_to_screen["_to_svc"]
        ]["cnt"].sum()
    )

    pooled = fn(cubes, **params).headline
    rows = []
    for service in sorted(by_service.index):
        volume = float(by_service[service])
        row = {"service": service, "cnt": volume,
               "share": volume / origin_total if origin_total else float("nan")}
        try:
            row.update(fn(_service_slice(cubes, service), **params).headline)
        except Exception as exc:  # 한 서비스가 죽어도 나머지는 낸다
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    frame = pd.DataFrame(rows)

    outside = {}
    for key, value in pooled.items():
        if key not in frame.columns:
            continue
        column = frame[key].dropna()
        if column.empty:
            continue
        lo, hi = float(column.min()), float(column.max())
        if value < lo or value > hi:
            outside[key] = (lo, hi)

    return ServiceBreakdown(
        frame=frame, pooled=pooled, outside_range=outside,
        cross_service_share=crossing / s2s_total if s2s_total else float("nan"),
        services=sorted(by_service.index),
    )
```

임포트는 `NON_SCREEN_STATES` 와 `service_of` 만 필요하다(`service_mix` 는 봉투가 쓴다):

```python
from analytics.metrics.services import NON_SCREEN_STATES, service_of
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests -q`
기대: `624 + 9(Task 1) + 8(Task 2) = 641 passed`, 4 skipped, 1 xfailed.

- [ ] **Step 5: mutation check**

`_service_slice` 의 `belongs("from_state") & belongs("to_state")` 를
`belongs("from_state")` 로 바꾸면(도착 화면 서비스를 안 보면) `top` 슬라이스에
`top/b -> media/x` 가 남아 `test_a_pooled_value_outside_the_service_range_is_flagged`
또는 기대 화면 수 값이 달라진다. `outside_range` 의 `value < lo or value > hi` 를
`value < lo` 로 바꾸면 `test_a_pooled_value_outside_the_service_range_is_flagged` 가
실패해야 한다(실측 상황이 **위로** 벗어나는 쪽이다).

- [ ] **Step 6: 커밋**

```bash
git add analytics/analyses/operators.py tests/analytics/analyses/test_per_service.py
git commit -m "feat: add the per_service operator and flag pooled values outside the range"
```

---

### Task 3: 봉투가 `service_mix` 를 싣는다

**왜:** `per_service` 를 **부른 사람만** 구성을 안다. 합산 결과를 그냥 받은 사람은 여전히
"앱 전체" 로 읽는다. 봉투는 이미 커버리지·사전 버전·날짜를 싣고 있으니 구성도 여기 넣는다.

**Files:**
- Modify: `analytics/analyses/base.py`
- Create: `tests/analytics/analyses/test_envelope_service_mix.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
"""봉투가 합산 지표의 서비스 구성을 싣는다."""
import pandas as pd
import pytest

from analytics.analyses.base import (
    REQUIRED_ENVELOPE_KEYS,
    CubeSet,
    envelope_for,
    get_analysis,
)

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _cubes(session=None, transition=None, quality=None) -> CubeSet:
    return CubeSet(session=session, transition=transition, quality=quality,
                   state_dict_version="sd_abc", services=["top", "media"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def _edges() -> pd.DataFrame:
    return pd.DataFrame([
        {**AXES, "from_state": "top/a", "to_state": "media/x", "cnt": 800,
         "dur_sum": 8000.0, "dur_n": 800},
        {**AXES, "from_state": "media/x", "to_state": "EXIT", "cnt": 200,
         "dur_sum": 2000.0, "dur_n": 200},
    ])


def test_the_envelope_carries_the_service_mix():
    got = envelope_for(_cubes(transition=_edges()), {})
    assert got["service_mix"] == {"top": pytest.approx(0.8),
                                  "media": pytest.approx(0.2)}


def test_a_shipped_analysis_carries_it_too():
    got = get_analysis("screen_flow")(_cubes(transition=_edges()))
    assert got.envelope["service_mix"]["top"] == pytest.approx(0.8)


def test_a_cube_without_a_transition_frame_gets_an_empty_mix():
    """세션 큐브만 있으면 서비스를 알 수 없다. 빈 dict 이고 0 으로 채우지 않는다."""
    session = pd.DataFrame([{**AXES, "sessions": 10, "uv": 5, "pv": 80,
                             "events": 300, "duration_sum": 6000}])
    assert envelope_for(_cubes(session=session), {})["service_mix"] == {}


def test_the_quality_cube_supplies_the_mix_when_there_are_no_edges():
    """품질 큐브에는 `service_code` 가 정식 컬럼으로 있다."""
    quality = pd.DataFrame([
        {"service_code": "top", "app_version": "9.5.1", "period": "2026-07-27",
         "check_name": "null_action_name", "violated": 1, "total": 800},
        {"service_code": "media", "app_version": "9.5.1", "period": "2026-07-27",
         "check_name": "null_action_name", "violated": 1, "total": 200},
    ])
    got = envelope_for(_cubes(quality=quality), {})
    assert got["service_mix"] == {"top": pytest.approx(0.8),
                                  "media": pytest.approx(0.2)}


def test_service_mix_is_not_required_to_publish():
    """세션 큐브만 있는 분석은 구성을 알 수 없다. 필수 키로 만들면 발행이 막힌다."""
    assert "service_mix" not in REQUIRED_ENVELOPE_KEYS
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_envelope_service_mix.py -q`
기대: 4개 실패(`KeyError: 'service_mix'`), `test_service_mix_is_not_required_to_publish` 통과.

- [ ] **Step 3: 구현 — `base.py`**

상단에 임포트를 추가한다:

```python
from analytics.metrics.services import service_mix
```

`envelope_for` 를 다음으로 바꾼다(기존 반환 dict 에 키 하나 추가 + 헬퍼):

```python
def _mix_of(cubes: CubeSet) -> dict[str, float]:
    """합산 지표의 서비스 구성. 알 수 없으면 빈 dict — 0 으로 채우지 않는다.

    전이 큐브는 화면 이름 접두어에서, 품질 큐브는 `service_code` 컬럼에서 읽는다.
    세션 큐브만 있으면 알 수 없다(세션 44.7%가 여러 서비스에 걸쳐 축이 될 수 없다).
    """
    if cubes.transition is not None:
        mix = service_mix(cubes.transition)
        if mix:
            return mix
    quality = cubes.quality
    if quality is not None and {"service_code", "total"} <= set(quality.columns):
        grouped = quality.groupby("service_code")["total"].sum()
        total = float(grouped.sum())
        if total > 0:
            return {str(k): float(v / total) for k, v in grouped.items()}
    return {}
```

그리고 반환 dict 에 한 줄 넣는다:

```python
        "coverage": dict(coverage),
        # 합산 지표가 어느 서비스에 붙어 있는지. 실측 15일 top 61.8% 대 content_v 2.1% 이고,
        # 이게 없으면 `mean_expected_steps` 10.62 가 "앱 전체" 로 읽힌다(서비스별 2.77~8.08).
        "service_mix": _mix_of(cubes),
        "warnings": list(warnings or []),
```

**`REQUIRED_ENVELOPE_KEYS` 는 건드리지 않는다** — 세션 큐브만 있는 분석은 구성을 알 수 없다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests -q`
기대: `641 + 5 = 646 passed`. 기존 봉투 테스트가 키 개수를 세고 있으면 함께 고친다 —
`grep -rn 'envelope\[' tests/ | head -30` 으로 먼저 확인한다.

- [ ] **Step 5: mutation check**

`_mix_of` 의 `return {}` 를 `return {"unknown": 1.0}` 으로 바꾸면
`test_a_cube_without_a_transition_frame_gets_an_empty_mix` 가 실패해야 한다.

- [ ] **Step 6: 커밋**

```bash
git add analytics/analyses/base.py \
        tests/analytics/analyses/test_envelope_service_mix.py
git commit -m "feat: carry the service mix in every envelope"
```

---

### Task 4: `cross_service_flow` — 감춰진 절반을 분석으로 꺼낸다

**왜:** 화면 간 전이의 **49.68%가 서비스를 건너뛴다.** 그게 이 앱의 실제 사용 행태인데
지금 어느 분석도 그걸 보여주지 않는다. `per_service` 는 그 절반을 **버리고** 비율만 알린다.
버린 것을 따로 보는 분석이 필요하다.

**Files:**
- Modify: `analytics/analyses/flow.py`
- Create: `tests/analytics/analyses/test_cross_service_flow.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
"""서비스 간 이동. 화면 간 전이의 절반이 여기 있다."""
import numpy as np
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _cubes(rows) -> CubeSet:
    edges = pd.DataFrame([
        {**AXES, "from_state": f, "to_state": t, "cnt": c,
         "dur_sum": float(c) * 10.0, "dur_n": c}
        for f, t, c in rows
    ])
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd_abc", services=["top", "media"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


# 화면->화면 400건 중 100건이 서비스를 건너뛴다 -> cross_service_share = 0.25
ROWS = [("START", "top/a", 50), ("top/a", "top/b", 300),
        ("top/b", "media/x", 100), ("media/x", "EXIT", 50)]


def test_one_row_per_service_pair():
    """`media/x -> EXIT` 는 도착이 화면이 아니라 빠진다 — media 출발 쌍이 생기지 않는다."""
    got = get_analysis("cross_service_flow")(_cubes(ROWS))
    pairs = set(zip(got.frame["from_service"], got.frame["to_service"]))
    assert pairs == {("top", "top"), ("top", "media")}


def test_the_frame_keeps_the_counts_and_the_within_share():
    got = get_analysis("cross_service_flow")(_cubes(ROWS)).frame.set_index(
        ["from_service", "to_service"]
    )
    assert got.loc[("top", "top"), "cnt"] == pytest.approx(300.0)
    assert got.loc[("top", "media"), "cnt"] == pytest.approx(100.0)
    # top 에서 출발한 400건 중 media 로 간 것이 100건
    assert got.loc[("top", "media"), "share_of_origin"] == pytest.approx(0.25)


def test_start_and_exit_are_excluded_because_they_have_no_service():
    """세션 경계는 서비스 간 이동이 아니다. 넣으면 분모가 세션 수만큼 부푼다."""
    got = get_analysis("cross_service_flow")(_cubes(ROWS))
    assert not {"START", "EXIT"} & set(got.frame["from_service"])
    assert not {"START", "EXIT"} & set(got.frame["to_service"])


def test_headline_cross_service_share():
    got = get_analysis("cross_service_flow")(_cubes(ROWS))
    assert got.headline["cross_service_share"] == pytest.approx(0.25)


def test_headline_switch_entropy_is_zero_when_every_switch_goes_one_way():
    """건너뛰는 이동이 한 쌍뿐이면 엔트로피 0 이다."""
    got = get_analysis("cross_service_flow")(_cubes(ROWS))
    assert got.headline["switch_entropy"] == pytest.approx(0.0)


def test_headline_switch_entropy_is_log_two_for_two_equal_switches():
    """서로 다른 두 이동이 반반이면 log(2) 다."""
    rows = [("top/a", "media/x", 100), ("media/x", "top/a", 100),
            ("top/a", "top/b", 200)]
    got = get_analysis("cross_service_flow")(_cubes(rows))
    assert got.headline["switch_entropy"] == pytest.approx(np.log(2))
    assert got.headline["cross_service_share"] == pytest.approx(0.5)


def test_switch_entropy_is_volume_weighted_not_a_count_of_pairs():
    """**대칭 픽스처로는 가중을 검증할 수 없다** — 반반이면 어떤 가중이든 log(2) 다.

    75:25 로 기울이면 갈린다: 물량 가중은 0.562335, 쌍 개수 기준(균등)은 log(2)=0.693147.
    앞 계획서에서 같은 함정을 밟아 mutation check 가 반만 들었다.
    """
    rows = [("top/a", "media/x", 300), ("media/x", "top/a", 100),
            ("top/a", "top/b", 600)]
    got = get_analysis("cross_service_flow")(_cubes(rows))
    p = np.array([0.75, 0.25])
    assert got.headline["switch_entropy"] == pytest.approx(-(p * np.log(p)).sum())
    assert got.headline["switch_entropy"] == pytest.approx(0.562335, abs=1e-6)


def test_a_single_service_cube_reports_zero_crossing_not_nan():
    """한 서비스만 있으면 건너뛰는 이동이 0 이다 — "모른다" 가 아니라 "없다"."""
    rows = [("START", "top/a", 10), ("top/a", "top/b", 90), ("top/b", "EXIT", 10)]
    got = get_analysis("cross_service_flow")(_cubes(rows))
    assert got.headline["cross_service_share"] == pytest.approx(0.0)
    assert got.headline["switch_entropy"] == pytest.approx(0.0)


def test_a_cube_with_no_screen_transitions_raises():
    rows = [("START", "EXIT", 10)]
    with pytest.raises(ValueError, match="no screen-to-screen transitions"):
        get_analysis("cross_service_flow")(_cubes(rows))
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_cross_service_flow.py -q`
기대: 전부 `UnknownAnalysisError: no analysis named 'cross_service_flow'`

- [ ] **Step 3: 구현 — `flow.py` 끝에 추가**

상단 임포트에 추가한다:

```python
from analytics.metrics.services import service_of
```

```python
@analysis("cross_service_flow")
def cross_service_flow(cubes: CubeSet, **_) -> AnalysisResult:
    """서비스 사이의 이동. **화면 간 전이의 절반이 여기 있다.**

    실측 15일에서 화면 간 전이 35.4억 건 중 49.68%가 서비스를 건너뛴다. 그게 이 앱의
    실제 사용 행태인데(세션 44.7%가 여러 서비스에 걸친다) 어느 분석도 보여주지 않았다 —
    `screen_flow` 는 화면 단위라 서비스가 안 보이고, `per_service` 는 이 전이를 **버린다.**

    `START`·`EXIT` 는 뺀다. 세션 경계는 서비스 간 이동이 아니고, 넣으면 분모가 세션
    수만큼 부푼다. `screen_pair_affinity` 가 둘을 넣는 것과 반대인데, 거기서는
    "어느 화면이 세션을 시작하는가" 가 답할 질문이었고 여기서는 아니다.

    `switch_entropy` 는 **건너뛰는 이동에 한정한** 목적지 분포의 엔트로피(nats)다.
    0 이면 모든 이동이 한 쌍으로만 가고, 크면 여러 방향으로 흩어진다. `cross_service_share`
    가 "얼마나 넘나드나" 이고 이쪽이 "어디로 넘나드나" 다.

    커버리지는 비운다 — 카운트만 쓴다.
    """
    edges = cubes.transition
    if edges is None:
        raise ValueError("cross_service_flow needs the transition cube; it is absent")
    frame = edges[["from_state", "to_state", "cnt"]].copy()
    frame["from_service"] = frame["from_state"].map(service_of)
    frame["to_service"] = frame["to_state"].map(service_of)
    frame = frame[frame["from_service"].notna() & frame["to_service"].notna()]
    if frame.empty or float(frame["cnt"].sum()) <= 0:
        raise ValueError(
            "no screen-to-screen transitions: every edge touches START or EXIT, so "
            "there is no service movement to report"
        )

    grouped = frame.groupby(["from_service", "to_service"], as_index=False)["cnt"].sum()
    origin = grouped.groupby("from_service")["cnt"].transform("sum")
    grouped["share_of_origin"] = grouped["cnt"] / origin
    grouped = grouped.sort_values("cnt", ascending=False, ignore_index=True)

    total = float(grouped["cnt"].sum())
    switches = grouped[grouped["from_service"] != grouped["to_service"]]
    switch_total = float(switches["cnt"].sum())
    if switch_total > 0:
        p = switches["cnt"].to_numpy(dtype=float) / switch_total
        entropy = float(-(p * np.log(p)).sum())
    else:
        # 건너뛰는 이동이 없다 = "없다" 이고 "모른다" 가 아니다. NaN 으로 내면 소비자가
        # 계측 실패와 구분할 수 없다.
        entropy = 0.0

    return AnalysisResult(
        frame=grouped,
        headline={
            "cross_service_share": switch_total / total,
            "switch_entropy": entropy,
        },
        envelope=envelope_for(cubes, {}, _thin_cell_warning(edges)),
        viz={"kind": "heatmap", "x": "from_service"},
    )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests -q`

`test_analyses_on_real_cubes.py::test_the_shipped_registry_is_what_it_should_be` 의
목록에 `cross_service_flow` 를 추가한다 — **이 테스트가 실패하는 것이 정상이고, 분석이
추가된 것을 눈에 띄게 하려고 있는 테스트다.** 알파벳 순서라 `cross_service_flow` 가
맨 앞이다:

```python
    assert _shipped_analyses() == [
        "cross_service_flow", "quality_report", "reachability",
        "screen_communities", "screen_dwell_rank", "screen_flow",
        "screen_pair_affinity", "session_trend",
    ]
```

기대: `646 + 9 = 655 passed`, 4 skipped, 1 xfailed.

- [ ] **Step 5: mutation check**

세 가지를 확인한다.

1. `frame[frame["from_service"].notna() & frame["to_service"].notna()]` 를
   `frame[frame["from_service"].notna()]` 로 바꾸면(도착의 `START`·`EXIT` 를 남기면)
   `test_start_and_exit_are_excluded_because_they_have_no_service` 가 실패해야 한다.
2. `switch_total / total` 을 `switch_total / switch_total` 로 바꾸면
   `test_headline_cross_service_share` 가 실패해야 한다.
3. **가중치 확인** — `p = switches["cnt"].to_numpy(...) / switch_total` 을
   `p = np.full(len(switches), 1.0 / len(switches))` (쌍 개수 균등)로 바꾸면
   `test_switch_entropy_is_volume_weighted_not_a_count_of_pairs` 가 실패해야 한다.
   **`log(2)` 테스트는 대칭이라 안 죽는다** — 그게 이 세 번째 확인을 따로 두는 이유다.

- [ ] **Step 6: 커밋**

```bash
git add analytics/analyses/flow.py \
        tests/analytics/analyses/test_cross_service_flow.py \
        tests/analytics/analyses/test_analyses_on_real_cubes.py
git commit -m "feat: add the cross_service_flow analysis over service movement"
```

---

### Task 5: 실데이터 회귀 그물 + SKILL.md

**왜:** 픽스처는 서비스가 둘이고 상태가 넷이다. 실큐브는 서비스 6개·상태 17개이고,
합산이 범위 밖으로 나가는 것은 **실큐브에서만** 나타난다.

**Files:**
- Modify: `tests/analytics/analyses/test_analyses_on_real_cubes.py`
- Modify: `.claude/skills/basic-analysis/SKILL.md`

- [ ] **Step 1: 실데이터 확인 스크립트 실행**

```python
# PYTHONPATH=. .venv/bin/python this_script.py
from analytics.analyses.base import get_analysis
from analytics.analyses.cubes import load_cube_set
from analytics.analyses.operators import per_service
from data_layer.config import Config

D = [f"2026-07-{d:02d}" for d in range(14, 29)]
S = ["top", "media", "entertain", "sports", "content_v", "search"]
cubes = load_cube_set(Config.from_env(), dates=D, services=S,
                      state_dict_version="sd_2ab5ec25e750dda2",
                      cube_names=("transition",))

for name in ("screen_flow", "screen_pair_affinity", "screen_dwell_rank"):
    got = per_service(cubes, name)
    print(f"\n=== {name} ===")
    print("pooled:", {k: round(v, 4) for k, v in got.pooled.items()})
    print("outside_range:", got.outside_range)
    print("cross_service_share:", round(got.cross_service_share, 4))
    print(got.frame.to_string(index=False))

flow = get_analysis("cross_service_flow")(cubes)
print("\n=== cross_service_flow ===")
print("headline:", {k: round(v, 6) for k, v in flow.headline.items()})
print(flow.frame.to_string(index=False))
print("envelope service_mix:",
      {k: round(v, 4) for k, v in flow.envelope["service_mix"].items()})
```

**`switch_entropy` 실측값은 아직 아무도 본 적이 없다.** 나오는 값을 실행 보고에 적는다.
`cross_service_share` 는 0.4968 근처여야 한다 — 다르면 `service_of` 나 분모를 점검한다.

- [ ] **Step 2: 회귀 그물 추가**

`test_analyses_on_real_cubes.py` 끝에 추가한다. 밴드는 Step 1 에서 나온 값으로 조여 넣되,
`switch_entropy` 는 처음 보는 값이므로 **성질만** 고정한다(0 초과, 유한).

```python
@needs_cubes
def test_the_pooled_flow_headline_sits_outside_every_service(real_cubes):
    """이 계획서를 쓴 이유. 합산 기대 화면 수가 여섯 서비스 전부보다 크다.

    실측: 합산 10.62 대 서비스별 2.77(content_v)~8.08(top). 화면 간 전이의 49.68%가
    서비스를 건너뛰어서, 합친 체인에는 어떤 단일 서비스 안에도 없는 전이가 있다.
    고정할 것은 크기가 아니라 **합산이 범위 밖이라는 사실**이다.
    """
    from analytics.analyses.operators import per_service

    got = per_service(real_cubes, "screen_flow")
    assert got.services == ["content_v", "entertain", "media", "search", "sports",
                            "top"]
    assert "mean_expected_steps" in got.outside_range
    lo, hi = got.outside_range["mean_expected_steps"]
    assert got.pooled["mean_expected_steps"] > hi
    assert 0.45 < got.cross_service_share < 0.55


@needs_cubes
def test_the_service_mix_shows_the_pooled_number_is_mostly_top(real_cubes, real_results):
    """실측 top 61.8% 대 content_v 2.1%. 봉투에 없으면 합산이 "앱 전체" 로 읽힌다."""
    mix = real_results["screen_flow"].envelope["service_mix"]
    assert set(mix) == {"top", "media", "entertain", "sports", "content_v", "search"}
    assert mix["top"] > 0.55
    assert sum(mix.values()) == pytest.approx(1.0)


@needs_cubes
def test_cross_service_movement_is_about_half_of_screen_transitions(real_results):
    """감춰져 있던 절반. `screen_flow` 는 화면 단위라 이걸 못 보여준다."""
    got = real_results["cross_service_flow"]
    assert 0.45 < got.headline["cross_service_share"] < 0.55
    assert got.headline["switch_entropy"] > 0, "여러 방향으로 흩어져야 한다"
    assert got.frame["cnt"].is_monotonic_decreasing
    assert set(got.frame["from_service"]) <= {"top", "media", "entertain", "sports",
                                              "content_v", "search"}
```

- [ ] **Step 3: 통과 확인**

Run: `.venv/bin/python -m pytest tests -q`
기대: `655 + 3 = 658 passed`, 4 skipped, 1 xfailed.

`_params_for` 가 `cross_service_flow` 에 파라미터를 주지 않아도 되는지 확인한다 —
필수 파라미터가 없으므로 `real_results` 픽스처가 그냥 돌아야 한다.

- [ ] **Step 4: SKILL.md 갱신**

1. 분석 표에 한 줄 추가한다:

```markdown
| `cross_service_flow` | transition | 서비스 쌍별 이동 건수·출발지 대비 비중 | `cross_service_share`·`switch_entropy` | — |
```

2. 연산자 절에 `per_service` 를 넣는다 — `compare`·`decompose` 와 같은 급이다:

```python
# 서비스별로 같은 분석을 돌린다 — 재빌드 없이 화면 이름 접두어에서 서비스를 읽는다
b = per_service(cubes, "screen_flow")
b.frame                 # 서비스별 headline + 물량·비중
b.pooled                # 합산 headline
b.outside_range         # 합산이 서비스별 범위 밖인 headline 키
b.cross_service_share   # 서비스별로 자를 때 사라진 전이 비중 (실측 0.4968)
```

3. **"Common mistakes" 에 항목을 추가한다:**

```markdown
- Reading a pooled screen-level headline as "the app". 실측 `mean_expected_steps` 는
  합산 10.62 인데 서비스별로는 2.77~8.08 이다 — **합산이 여섯 전부보다 크다.** 화면 간
  전이의 49.68%가 서비스를 건너뛰어서 합친 체인에만 있는 전이가 들어 있다. 봉투의
  `service_mix` 가 구성을 말해주고(top 61.8%), `per_service` 의 `outside_range` 가
  이 상황을 자동으로 표시한다. 서비스 간 이동 자체는 `cross_service_flow` 로 본다.
- Comparing the same screen name across services. `m_newsview_보기` 를 media·entertain·
  sports 세 팀이 쓴다. 서비스 접두어로 분리돼 있지만 **계측 방식이 다르다** — 이름 하나가
  여러 페이지를 가리키는 비율이 sports 28.7%, entertain 0.01% 다.
```

4. "실측 규모" 표에 `cross_service_flow` 를 넣는다(Step 1 에서 나온 소요·대표값으로).

- [ ] **Step 5: 커밋**

```bash
git add tests/analytics/analyses/test_analyses_on_real_cubes.py \
        .claude/skills/basic-analysis/SKILL.md
git commit -m "test: pin that the pooled flow headline sits outside every service"
```

---

## 완료 기록 (2026-07-30, Task 1~5)

**Task 1~5 전부 완료.** 전체 스위트 **662 passed, 4 skipped, 1 xfailed** (16.9초).
분석 8개(`cross_service_flow` 추가) + 연산자 3개(`per_service` 추가).
커밋: `bc6eb6d` · `48e969b` · `03dec4b` · `30c8032` · `9d65a01`.

### 실데이터에서 처음 나온 숫자

**`switch_entropy` = 2.220438 nats.** 건너뛰는 쌍이 30개라 최대 ln(30)=3.401 의 **65%** —
서비스 간 이동이 한 경로로 몰리지 않고 여러 방향으로 흩어진다.

**작은 서비스는 top 으로 흘러간다** (출발지 대비 비중, 새 관찰):
media→top **71.7%**, content_v→top **75.4%**, entertain→top 62.2%, sports→top 59.8%.
top 은 60.3% 를 자기 안에 두고 search 는 59.6% 가 자기 루프(화면이 하나뿐이다).
**합산 지표에서는 안 보이고 `per_service` 는 이 전이를 버리므로**, `cross_service_flow`
가 유일하게 보여주는 자리다.

**벗어나는 방향이 양쪽 다 실재한다:** `mean_expected_steps` 합산 10.62 > 최대 8.08,
`mean_exit_prob` 합산 0.0975 < 최소 0.1407.

**`outside_range` 는 무조건 울리는 경보가 아니다.** `screen_dwell_rank` 는 빈다 —
방문당 체류가 물량 가중 평균이라 정의상 범위 안이다(합산 48.42, 서비스별 35.69~73.29).
그래서 `screen_flow` 가 걸리는 건 체인 길이라는 지표의 성질이고 분해의 부작용이 아니다.

### 계획서 코드에 있던 조용한 결함

**`service_mix` 의 모양이 틀렸고 스위트가 2.6배 느려졌다(11.7 → 30.4초).** 봉투마다
불리는 함수인데 계획서 코드가 행마다 문자열을 잘랐다. 고치는 데 세 번 걸렸고 순서가
교훈이다:

| 방식 | 실측 328만 행 |
|---|---|
| 계획서 그대로 (`[service_of(s) for s in ...]`) | 1.90s |
| `str.split` 벡터화 | 1.38s |
| 유일값에만 계산하고 매핑 (상태 16개) | 0.40s |
| **먼저 상태로 묶고 서비스로 접기** | **0.05s** |

구현이 아니라 **일의 모양**이 문제였다. 행은 328만인데 상태는 16개다. 벡터화만으로는
27%밖에 못 줄였고, 행 단위 중간 시리즈를 아예 만들지 않는 게 답이었다.
`per_service` 도 같은 이유로 5.5 → 1.9초(서비스마다 다시 계산하던 것을 한 번만).

### 계획서 픽스처가 통과를 거짓으로 만든 곳

**Task 2 픽스처의 top 슬라이스에 `EXIT` 로 가는 길이 없었다.** `screen_flow` 가
`KeyError: unknown state: 'EXIT'` 로 죽어 top 행이 NaN 이 되고, `outside_range` 가
**살아남은 media 한 줄만** 보고 "범위 밖" 이라고 말했다. 테스트는 통과했지만 이유가
행동과 무관했다.

**mutation check 가 그것을 "안 잡힘" 으로 드러냈다** — 도착 서비스 필터를 지워도 아무
테스트가 안 죽었는데, 슬라이스가 이미 망가져 있었기 때문이다. 두 서비스가 각자 `EXIT` 로
나가면서 서로 오가는 픽스처로 바꾸자(합산 8.86 대 1.00~1.75) 네 mutation 전부 잡혔다.
**"mutation 이 안 잡힌다" 는 테스트가 약하다는 신호가 아니라 픽스처가 죽어 있다는 신호일
수 있다.**

### 계획서의 mutation check 가 틀렸던 곳

**Task 4 의 "도착 필터를 지우면 `START`·`EXIT` 가 남아 테스트가 실패한다" 는 틀렸다.**
`groupby` 가 NaN 키를 기본으로 버려서 그 필터는 **관측되지 않는다.** 관측되는 경우가
하나 있고 그걸 테스트로 고정했다: 화면이 `EXIT` 로만 나가는 큐브
(`top/a -> EXIT` 하나)는 출발만 보면 프레임이 비지 않아 통과하고, groupby 가 그 행을
버려 분모가 0 이 되어 거부해야 하는 자리에서 `ZeroDivisionError` 가 난다.

### 자체 검토가 구현 전에 잡은 것

계획서를 쓰고 다시 읽는 단계에서 둘을 고쳤다 — **분모 두 종류를 섞은 것**(`share` 는
화면 출발, `cross_service_share` 는 화면→화면인데 `cnt` 를 `mix × total` 로 되돌려
계산해 물량이 틀렸다)과 **있을 수 없는 `(media, media)` 쌍을 기대한 픽스처**(그 서비스의
유일한 엣지가 `EXIT` 로 끝나서 도착이 화면이 아니다).

### 문서로만 남긴 것

`per_service` 의 `dwell_coverage` 는 **서비스 내부 전이만**의 커버리지다(top 51.5%).
서비스에서 출발한 전이 전체로 재면 top 64.7% 다 — 서비스를 건너뛰는 전이가 더 잘
계측돼 있기 때문이다. 둘 다 옳은 값이라 코드를 고치지 않고 SKILL.md 의
"Common mistakes" 에 갈라 적었다. **계측 수준을 물으면 후자, 슬라이스한 체인의 신뢰도를
물으면 전자다.**

---

## 이 계획서가 끝난 뒤 남는 것

| | 무엇 | 선행 조건 |
|---|---|---|
| **B** | 3단계 행동층 — `plans/2026-07-29-action-layer-phase3.md` Task 2~8. **Task 1 은 완료**(측정 문서 2개). Task 2·3 을 `visit_idx` + `click.layer1` 기준으로 고쳐 쓰고 Task 5~8 본문을 채운 뒤 진행 | Trino. 행동층 큐브의 `screen` 은 전이 큐브와 **같은 식**을 쓴다 |
| A4-full | 세션 큐브에 `(period, app_version)` grouping set → `uv` 를 버전별로 | 세션 큐브 15일 재빌드 ≈1.3시간. **요구가 실제로 생길 때만** |
| A6 | `screen_dwell_rank` 가 서비스가 다른 화면을 한 표에 순위 매기는 것 | 이 계획서로 `service_mix` 는 붙지만 **코드가 막지는 않는다.** 프레임에 `service` 열을 넣고 서비스별 커버리지를 함께 낼지는 별건 |
| C | 4단계 대시보드 | 계획서 없음 |
| D-1~4 | state 사전 가중치·고차 마르코프·DiD·큐브 날짜 확장 | 앞 계획서 표 참고 |

**사전 채택이 작은 서비스를 굶긴다** — 새로 확인된 항목이다. 채택 컷이 **전체 물량** 누적
95%라 top 이 물량의 56%를 차지하면서 작은 서비스가 먼저 잘린다. 결과가 sports `/other`
37.0%, entertain 18.7% 다. **서비스별로 95% 컷을 걸면** 각 서비스가 자기 머리를 받는다.
큐브 재빌드가 필요하고(사전 버전이 캐시 키에 들어간다) 상태 수가 늘어 전이 큐브가 커진다 —
A5 를 끝내고 서비스별 값을 본 뒤에 판단한다.

## 이 층에서 특히 의심할 자리

1. **`service_type` 과 `service_code` 를 섞지 말 것** (함정 11). 전자는 `MA`·`MW`·`PW`.
2. **`service_code` 를 축으로 올리지 말 것** (함정 12). 세션이 쪼개지고 15일 재빌드다.
3. **서비스별 합은 합산과 안 맞는다** (함정 13). 절반이 서비스를 건너뛴다. 비율을 함께 낸다.
4. **모르는 것은 빈 dict·NaN 이다.** 세션 큐브만 있으면 `service_mix` 는 `{}` 이고
   `{"unknown": 1.0}` 이 아니다. 건너뛰는 이동이 **없는** 것은 0 이고 NaN 이 아니다.
5. **대칭적인 픽스처는 가중을 검증하지 못한다.** 앞 계획서에서 `cnt` 가 같은 두 쌍으로
   물량 가중을 검증하려다 반만 들었다. `switch_entropy` 테스트도 같은 함정이 있으니
   `log(2)` 픽스처 하나로 만족하지 말고 비대칭 케이스를 함께 둔다.

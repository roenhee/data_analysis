# 분석층 잔여 작업 (A3·A4) Implementation Plan

> **완료 (2026-07-30).** Task 1~3 전부 끝났다 — 624 passed. 아래 본문은 당시 판단
> 기록이고, **계획서가 틀렸던 곳은 "완료 기록" 절**에 모아 뒀다. 이 문서를 참고로 쓰는
> 사람은 그 절을 먼저 읽는다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세션 큐브 지표를 세그먼트로 비교할 수 있게 하고(`uv` 는 정직하게 NaN), PMI 를
이름 붙은 분석으로 만들어 발행 가능하게 한다.

**Architecture:** 이미 있는 `analytics/analyses/` 위에서만 작업한다. 큐브 재빌드도 Trino 도
필요 없다 — 세션 큐브에서 비가산인 것은 `uv` 하나뿐이고, `sessions`·`pv`·`events`·
`duration_sum` 은 전체 조합 행을 합해도 맞기 때문이다.

**Tech Stack:** Python 3.14, pandas 3.0.3, numpy 2.5.1, pytest. 새 의존 없음.

**선행 계획서:** `docs/superpowers/plans/2026-07-29-analyses-layer.md` (Task 1~11 완료).
그 문서 상단 "완료 기록" 절에 **계획서가 틀렸던 곳**이 정리돼 있다 — 먼저 읽는다.

---

## 시작 절차 (그대로 실행)

```bash
.venv/bin/python -m pytest tests -q
```

기대: `603 passed, 4 skipped, 1 xfailed` (약 10초. 실큐브 테스트가 9초를 쓴다).
숫자가 다르면 **작업을 시작하기 전에** 원인을 찾는다.

```bash
git log --oneline -1     # 76aac19 docs: record the A1 and A2 outcomes ...
git status -sb           # master...origin/master, 추적 안 되는 .DS_Store 하나
```

실데이터로 확인할 때 쓰는 좌표 — **이 세 값은 함께 맞아야 한다**:

```python
dates = [f"2026-07-{d:02d}" for d in range(14, 29)]        # 15일치가 빌드돼 있다
services = ["top", "media", "entertain", "sports", "content_v", "search"]
state_dict_version = "sd_2ab5ec25e750dda2"
```

```python
# PYTHONPATH=. .venv/bin/python this_script.py
from analytics.analyses.cubes import load_cube_set
from data_layer.config import Config
cubes = load_cube_set(Config.from_env(), dates=dates, services=services,
                      state_dict_version=state_dict_version)
```

## 반드시 알아야 하는 함정 — 전부 2026-07-29 에 실제로 밟았다

1. **`services` 목록이 빌드와 다르면 큐브를 못 찾는다.** 서비스 목록이 `sql_hash` 에
   들어간다. `services=["top"]` 으로 부르면 `CubeNotBuiltError` 다 — 큐브가 없는 게
   아니라 키가 다른 것이다. 위의 6개를 그대로 쓴다.
2. **테스트용 가짜 분석이 전역 레지스트리에 있다.** `fake_steps`·`fake_steps_power`·
   `dummy_*` 가 연산자 테스트에서 등록된다. 파일 하나만 돌릴 때는 안 보이고 **전체
   스위트에서만** 섞여 든다. 레지스트리를 순회하려면
   `get_analysis(n).__module__.startswith("analytics.analyses.")` 로 가른다
   (`tests/analytics/analyses/test_analyses_on_real_cubes.py::_shipped_analyses`).
3. **`tests/` 를 `sys.path` 에 넣으면 `tests/analytics/` 가 진짜 `analytics/` 를 가린다.**
   mutation check 스크립트에서 테스트 모듈의 픽스처를 임포트하지 말고 스크립트 안에
   다시 정의한다.
4. **독립 스크립트는 `PYTHONPATH=.` 가 필요하다.** 없으면 `ModuleNotFoundError: analytics`.
5. **pandas 3.0**: 문자열 컬럼의 `None` 은 읽을 때 NaN 이다 — `is None` 이 아니라
   `pd.isna()` 로 본다. 길이 1 리스트로 `groupby` 하면 키가 1-튜플로 온다.
6. **집합은 절대 그대로 기록·비교하지 않는다.** `repr` 순서가 프로세스마다 다르다
   (해시 시드 3개로 확인). `base._canonical` 이 정렬해 준다.
7. **Louvain 은 노드 삽입 순서로 답이 바뀐다 — 시드를 고정해도.** 같은 그래프(가중치
   다른 엣지 0개)에서 군집 4개(Q=0.395878) 대 3개(Q=0.394087) 가 나왔다.
   `communities._screen_graph` 가 정렬로 막는다.
8. **잔차로 정의된 값에 항등식 테스트를 쓰지 말 것.** `between = pooled − within` 이라
   `within` 이 무엇이든 `within + between == pooled` 는 성립한다. 계획서에 적혀 있던
   mutation check 가 이래서 무력했다. 값을 고정하려면 **부호까지 갈리는 픽스처**를 쓴다.
9. **금지된 git 명령**: `git add -A`(추적 안 되는 `.DS_Store` 가 있다),
   `git reset --hard`, `git checkout <path>`, `git stash`, `git restore`.
10. **크레덴셜을 `$()` 로 셸에 끌어내면 권한 분류기가 막는다.** `.venv/bin/python -c '...'`
    안에서 `import env` 후 `os.environ` 에 직접 넣는다.

### mutation check 하는 법 (이 패턴을 그대로 쓴다)

파일을 고쳐 넣고 pytest 를 돌린 뒤 `finally` 에서 되돌린다. git 으로 되돌리지 않는다.

```bash
python3 - <<'EOF'
import pathlib, subprocess
p = pathlib.Path("analytics/analyses/operators.py")
src = p.read_text()
before, after = '<원래 줄>', '<결함 주입한 줄>'
assert before in src
try:
    p.write_text(src.replace(before, after))
    r = subprocess.run([".venv/bin/python", "-m", "pytest",
                        "tests/analytics/analyses/test_decompose.py", "-q"],
                       capture_output=True, text=True)
    print("\n".join(l for l in r.stdout.splitlines()
                    if l.startswith("FAILED") or " passed" in l))
finally:
    p.write_text(src)
    print("복원 완료")
EOF
```

## 지금 상태 — 전부 2026-07-29 실측

분석 6개 + 연산자 2개 + 로더. 15일치 큐브(전이 3,279,905 / 세션 214,668 / 품질 251,822 행),
화면은 사전에 **15개**뿐이라 프레임이 작다. 비용은 프레임이 아니라 큐브 행 수에서 온다.

| 분석 | 소요 | 대표값 |
|---|---|---|
| `session_trend` | 0.14s | 세션 490,987,437 · 세션당 PV 8.0 · 체류 556.64초 |
| `screen_dwell_rank` | 0.24s | 방문당 48.42초 · 커버리지 0.5651 |
| `screen_flow` | 0.32s | 기대 걸음 수 10.62 · 이탈확률 0.0975 |
| `quality_report` | 0.36s | 이탈 뒷받침 0.8922 · 화면 커버리지 0.7796 |
| `screen_communities` | 0.48s | 군집 3개 · modularity 0.394 |
| `load_cube_set` (15일 3큐브) | 1.7s | |
| `compare` (15일 두 세그먼트) | 5.8s | 날짜별로 분석을 다시 돌려서 가장 비싸다 |

**버전 비교 회귀 그물** (9.5.1 vs 9.5.0, `service_type="MA"`, 배포일 컷오프):
날짜별 +9.18 / +4.46 / +6.80%, 합산 **+0.71%**, `within +7.50%` / `between −6.79%`,
`weight_skew 0.5768`. 계획서가 적어 둔 "합산 음수" 는 **재현되지 않는다** — 부호가
뒤집히는 게 아니라 구성 변화가 효과의 90%를 먹는다. 대조군으로 성별 비교(F vs M)는
15일 내내 −26.05~−20.95%, `weight_skew 0.009` 로 부호가 안 바뀐다.

**상시 품질 경고 4건** (60행 · 8.8 KB): `search` 체류 계측 없음(1.0000, 15일),
`top` 화면 없는 세션 0.1960~0.3262, `page_name_ambiguous` search 0.6958~0.7930 ·
sports 0.2714~0.3532. 넷 다 실재하는 결함이라 매일 걸리게 두었다.

## File Structure

| 파일 | 이 계획서에서 하는 일 |
|---|---|
| `analytics/analyses/operators.py` | 물량 컬럼을 큐브별로 고른다 (Task 1) |
| `analytics/analyses/descriptive.py` | `session_trend` 가 슬라이스에서도 돈다 (Task 2) |
| `analytics/analyses/flow.py` | `screen_pair_affinity` 추가 (Task 3) |
| `tests/analytics/analyses/test_compare_on_session_cubes.py` | Task 1·2 의 새 테스트 |
| `tests/analytics/analyses/test_session_trend.py` | 슬라이스 fallback 테스트 추가 (Task 2) |
| `tests/analytics/analyses/test_screen_pair_affinity.py` | Task 3 |

> **미검증 가설 표시.** 아래 Task 1·2 의 **동작**(슬라이스에서 롤업 행이 없어 fallback
> 경로를 탄다)은 코드를 읽고 추론한 것이고 **아직 실행하지 않았다.** 픽스처의 숫자는
> 손으로 계산한 값이라 맞지만, 경로가 예상대로 갈리는지는 Step 2 의 실패 확인에서
> 처음 드러난다. 예상과 다르면 계획서를 고치고 진행한다 — 오늘 이 프로젝트에서
> 계획서를 믿고 따라간 것이 문제였다.

---

### Task 1: 물량 컬럼을 큐브별로 고른다

**왜:** `compare` 는 날짜 가중치를 `weight_skew(..., measure="cnt")` 로 재는데 `cnt` 는
전이 큐브에만 있다. 세션 큐브 분석에 걸면 `KeyError: 'cnt'` 다. 그리고 세션 큐브를
그냥 세면 `GROUPING SETS` 롤업 행 때문에 물량이 grouping set 수만큼 부푼다.

**Files:**
- Modify: `analytics/analyses/operators.py`
- Create: `tests/analytics/analyses/test_compare_on_session_cubes.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/analyses/test_compare_on_session_cubes.py`:

```python
"""세션 큐브 분석을 연산자에 걸 수 있는가. 물량 컬럼이 큐브마다 다른 것이 요점이다."""
import numpy as np
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis
from analytics.analyses.operators import compare, decompose

AXES = ("period", "service_type", "os", "gender", "age_band", "daypart",
        "app_version")

# 하루 · 버전당: 전체 조합 행 둘(gender M/F, 각 100세션) + gender 를 접은 행 하나(200세션).
# 접은 행은 app_version 을 그대로 갖고 있어서, 전체 조합 행만 세지 않으면 물량이 2배가 된다.
# 9.5.0 은 세션당 600초, 9.5.1 은 660초 -> 델타 +10% (두 날 모두).
def _session_cube() -> pd.DataFrame:
    base = dict(service_type="MA", os="android", age_band="50", daypart="12~17")
    rows = []
    for day in ("2026-07-27", "2026-07-28"):
        for version, seconds in (("9.5.0", 600.0), ("9.5.1", 660.0)):
            for gender in ("M", "F"):
                rows.append({**base, "period": day, "gender": gender,
                             "app_version": version, "sessions": 100, "uv": 60,
                             "pv": 800, "events": 3000,
                             "duration_sum": int(100 * seconds)})
            rows.append({**base, "period": day, "gender": None,
                         "app_version": version, "sessions": 200, "uv": 110,
                         "pv": 1600, "events": 6000,
                         "duration_sum": int(200 * seconds)})
        # (period) 롤업 행 — 자르지 않은 프레임에서 uv 를 읽는 행
        rows.append({**{a: None for a in AXES}, "period": day, "sessions": 400,
                     "uv": 200, "pv": 3200, "events": 12000,
                     "duration_sum": 252_000})
    return pd.DataFrame(rows)


def _cubes() -> CubeSet:
    days = ["2026-07-27", "2026-07-28"]
    return CubeSet(session=_session_cube(), transition=None, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=days, present_dates=days)


def test_a_session_cube_analysis_can_be_compared():
    got = compare(_cubes(), "session_trend", on="app_version", a="9.5.1", b="9.5.0")
    assert got.dates_used == ["2026-07-27", "2026-07-28"]
    assert got.pooled["seconds_per_session"] == pytest.approx(0.1)
    assert got.per_day["delta_seconds_per_session"].tolist() == pytest.approx([0.1, 0.1])
    assert got.sign_disagrees is False


def test_the_day_weights_count_sessions_not_transitions():
    """전이 큐브에만 있는 `cnt` 로 세면 `KeyError` 다. 세션 큐브는 `sessions` 로 센다."""
    got = compare(_cubes(), "session_trend", on="app_version", a="9.5.1", b="9.5.0")
    assert got.weight_skew == pytest.approx(0.0)


def test_the_stratum_volume_excludes_rollup_rows():
    """롤업 행을 함께 세면 물량이 2배가 된다 — 사람이 읽는 표에 없는 세션이 실린다."""
    c = compare(_cubes(), "session_trend", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(_cubes(), c, by=["period"], metric="seconds_per_session")
    per = d.per_stratum.set_index("period")
    assert per.loc["2026-07-27", "a_cnt"] == pytest.approx(200.0)
    assert per.loc["2026-07-27", "b_cnt"] == pytest.approx(200.0)


def test_the_decomposition_identity_holds_on_a_session_cube():
    c = compare(_cubes(), "session_trend", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(_cubes(), c, by=["period"], metric="seconds_per_session")
    assert d.within + d.between == pytest.approx(c.pooled["seconds_per_session"],
                                                 abs=1e-9)
    assert d.within == pytest.approx(0.1)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_compare_on_session_cubes.py -q`

기대: 4개 실패. `test_a_session_cube_analysis_can_be_compared` 는
`NonAdditiveMeasureError`(Task 2 가 고친다)나 `KeyError: 'cnt'` 로 죽는다.
**둘 중 무엇이 먼저 나는지 기록해 둔다** — 어느 쪽이든 Task 1·2 를 둘 다 해야 통과한다.
`KeyError: 'cnt'` 가 먼저 난다면 Task 1 을 먼저, `NonAdditiveMeasureError` 가 먼저
난다면 Task 2 를 먼저 해도 된다. 순서는 결과에 영향이 없다.

- [ ] **Step 3: 구현 — `operators.py`**

`VOLUME_COLUMN = "cnt"` 상수와 `_primary_cube` 를 다음으로 **대체**한다:

```python
from analytics.metrics.descriptive import SESSION_AXES
from analytics.metrics.frame import full_combination_rows

def _volume_frame(cubes: CubeSet) -> tuple[pd.DataFrame, str]:
    """날짜·층 가중치를 셀 프레임과 그 컬럼.

    전이 큐브는 `cnt`, 세션 큐브는 `sessions` 다. **세션 큐브는 전체 조합 행만 쓴다** —
    `GROUPING SETS` 롤업 행이 같은 파일에 있어서 그냥 세면 grouping set 수만큼 부푼다.
    비중만 보는 `weight_skew` 는 그 부풀림에 둔감할 수 있지만, `decompose` 가 표에
    싣는 `a_cnt`·`b_cnt` 는 사람이 읽는 절대 물량이라 틀리면 안 된다.
    """
    if cubes.transition is not None:
        frame, measure, which = cubes.transition, "cnt", "transition"
    elif cubes.session is not None:
        frame = full_combination_rows(cubes.session, SESSION_AXES)
        measure, which = "sessions", "session"
    else:
        raise ValueError(
            "no cube to compare on: both transition and session are absent"
        )
    if measure not in frame.columns:
        raise ValueError(
            f"the {which} cube has no {measure!r} column "
            f"(has: {', '.join(map(str, frame.columns))}); weighting by zero would "
            "report the whole delta as composition rather than refusing"
        )
    return frame, measure
```

`compare` 안에서:

```python
    fn = get_analysis(analysis_name)
    cube, measure = _volume_frame(cubes)
    days = comparable_dates(cube, on, a, b, released=released)
```

그리고 `weight_skew` 호출에 `measure=measure` 를 넘긴다:

```python
        weight_skew=weight_skew(cube, on, a, b, measure=measure, released=released),
```

`decompose` 안에서 `VOLUME_COLUMN` 을 쓰던 세 곳을 바꾼다:

```python
    cube, measure = _volume_frame(cubes)
    scoped = cubes.filter(dates=comparison.dates_used)
    ...
        ca = float(_volume_frame(sa)[0][measure].sum())
        cb = float(_volume_frame(sb)[0][measure].sum())
```

앞쪽의 `if VOLUME_COLUMN not in cube.columns: raise ValueError(...)` 블록은 지운다 —
`_volume_frame` 이 이미 검사한다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses -q`

기대: Task 2 를 마치기 전이면 `test_a_session_cube_analysis_can_be_compared` 만 남아
실패한다(`NonAdditiveMeasureError`). 기존 `test_decompose.py` 의
`test_a_cube_without_a_volume_column_is_refused` 는 계속 통과해야 한다 —
메시지에 `cnt` 가 남아 있어야 `match="cnt"` 가 맞는다.

- [ ] **Step 5: mutation check**

`full_combination_rows(cubes.session, SESSION_AXES)` 를 `cubes.session` 으로 바꾸면
`test_the_stratum_volume_excludes_rollup_rows` 가 400 대 200 으로 실패해야 한다.
`measure=measure` 를 지우면(=`"cnt"` 기본값) `test_the_day_weights_count_sessions_not_transitions`
가 `KeyError: 'cnt'` 로 실패해야 한다.

- [ ] **Step 6: 커밋** (Task 2 까지 끝낸 뒤 함께 커밋해도 된다)

---

### Task 2: `session_trend` 가 세그먼트 슬라이스에서도 돈다

**왜:** 버전으로 자르면 `(period)` 롤업 행이 사라진다(그 행은 `app_version` 이 NULL 이라
값으로 필터하면 빠진다). 지금은 `NonAdditiveMeasureError` 로 죽는다. 그런데 **비가산인
것은 `uv` 하나뿐**이다 — 세션은 first-event 로 귀속되므로 전체 조합 격자에서 정확히 한
칸에만 들어가고, `sessions`·`pv`·`events`·`duration_sum` 은 합해도 맞다. 기존 테스트
`tests/analytics/metrics/test_metrics_on_real_cubes.py::test_the_filtered_sum_matches_the_grand_total_row`
가 실큐브에서 그걸 확인한다.

**Files:**
- Modify: `analytics/analyses/descriptive.py`
- Modify: `tests/analytics/analyses/test_session_trend.py`

- [ ] **Step 1: 실패하는 테스트 작성** — `test_session_trend.py` 끝에 추가

```python
def test_a_segment_slice_still_gives_the_additive_measures():
    """버전으로 자르면 `(period)` 롤업 행이 사라진다. 가산 측정값은 그대로 낼 수 있다."""
    from tests.analytics.analyses.test_compare_on_session_cubes import _cubes

    sliced = _cubes().filter(app_version="9.5.1")
    got = get_analysis("session_trend")(sliced).frame.set_index("period")
    # 전체 조합 행만 합한다: gender M 100 + F 100 = 200 (gender 접은 200 을 더하면 400)
    assert int(got.loc["2026-07-27", "sessions"]) == 200
    assert int(got.loc["2026-07-27", "duration_sum"]) == 132_000
    assert got.loc["2026-07-27", "seconds_per_session"] == pytest.approx(660.0)


def test_uv_is_nan_on_a_slice_rather_than_a_sum():
    """`uv` 를 합하면 실측 1.71배로 부푼다. 모르는 것은 NaN 이다."""
    from tests.analytics.analyses.test_compare_on_session_cubes import _cubes

    sliced = _cubes().filter(app_version="9.5.1")
    got = get_analysis("session_trend")(sliced)
    assert got.frame["uv"].isna().all()
    assert pd.isna(got.frame["sessions_per_user"].iloc[0])


def test_the_envelope_says_uv_could_not_be_read_for_the_slice():
    from tests.analytics.analyses.test_compare_on_session_cubes import _cubes

    sliced = _cubes().filter(app_version="9.5.1")
    got = get_analysis("session_trend")(sliced)
    assert [w["check_name"] for w in got.envelope["warnings"]] == [
        "uv_unavailable_for_this_slice"
    ]


def test_an_unsliced_cube_still_reads_uv_from_the_rollup_row():
    """fallback 이 생겼다고 자르지 않은 경우까지 합산으로 가면 안 된다."""
    got = get_analysis("session_trend")(_cubes()).frame.set_index("period")
    assert int(got.loc["2026-07-27", "uv"]) == 60
    assert not get_analysis("session_trend")(_cubes()).envelope["warnings"]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_session_trend.py -q`
기대: 새 테스트 3개가 `NonAdditiveMeasureError` 로 실패,
`test_an_unsliced_cube_still_reads_uv_from_the_rollup_row` 는 통과.

- [ ] **Step 3: 구현 — `descriptive.py`**

`session_trend` 의 날짜 루프에서 측정값을 만드는 부분을 헬퍼로 뺀다:

```python
import numpy as np
from analytics.metrics.frame import full_combination_rows, rollup_rows


def _day_measures(one: pd.DataFrame, folded: tuple[str, ...]) -> tuple[dict, bool]:
    """하루치 측정값과 "슬라이스라 `uv` 를 못 읽었는가".

    롤업 행이 있으면 그걸 읽는다. 세그먼트로 자른 프레임에는 없으므로(롤업 행은 접힌
    축이 NULL 이라 값으로 필터하면 사라진다) **가산 측정값만 전체 조합 행에서 합하고
    `uv` 는 NaN 이다** — 합하면 실측 1.71배로 부푼다. 전체 조합 행만 합하는 것도
    중요하다: 축 하나를 접은 행이 같은 파일에 있어서 그냥 합하면 두 번 센다.
    """
    rollup = rollup_rows(one, SESSION_AXES, folded=folded)
    if not rollup.empty:
        base = uv_pv(one, folded=folded).iloc[0]
        eng = engagement(one, folded=folded).iloc[0]
        return {
            "sessions": int(base["sessions"]), "uv": float(base["uv"]),
            "pv": int(base["pv"]), "events": int(base["events"]),
            "duration_sum": int(rollup["duration_sum"].iloc[0]),
            "sessions_per_user": float(eng["sessions_per_user"]),
            "pv_per_session": float(eng["pv_per_session"]),
            "seconds_per_session": float(eng["seconds_per_session"]),
        }, False

    full = full_combination_rows(one, SESSION_AXES)
    sessions = float(full["sessions"].sum())
    pv = float(full["pv"].sum())
    duration = float(full["duration_sum"].sum())
    return {
        "sessions": int(sessions), "uv": np.nan,
        "pv": int(pv), "events": int(full["events"].sum()),
        "duration_sum": int(duration),
        # uv 가 없으면 유저당 세션의 분모가 없다. 0 도 아니고 1 도 아니다.
        "sessions_per_user": np.nan,
        "pv_per_session": pv / sessions if sessions else np.nan,
        "seconds_per_session": duration / sessions if sessions else np.nan,
    }, True
```

그리고 `session_trend` 본문:

```python
    folded = tuple(a for a in SESSION_AXES if a != "period")
    rows, sliced = [], False
    for day in sorted(set(cubes.session["period"].dropna())):
        one = cubes.session[cubes.session["period"] == day]
        measures, without_uv = _day_measures(one, folded)
        sliced = sliced or without_uv
        row = {"period": day, **measures,
               "dwell_definition": DWELL_DEFINITION}
        if holidays is not None:
            row["day_kind"] = day_kind(day, holidays)
        rows.append(row)
    frame = pd.DataFrame(rows)

    warnings = []
    if sliced:
        warnings.append({
            "check_name": "uv_unavailable_for_this_slice",
            "reason": "the cube has no rollup row for this segment, and uv cannot be "
                      "summed into one — it inflated 1.71x on the real cube",
        })
```

`DWELL_DEFINITION` 은 `analytics.metrics.descriptive` 에서 임포트한다(지금은
`engagement` 가 내는 컬럼을 그대로 옮겨 담고 있는데, fallback 경로에는 `engagement`
결과가 없으므로 상수를 직접 쓴다).

headline 은 **바꾸지 않는다** — `sessions`·`pv`·`duration_sum` 합에서 나오므로 두
경로 모두에서 성립한다. `uv` 는 원래 headline 에 없다.

봉투는 `envelope_for(cubes, demography_coverage(cubes.session), warnings)` 로 바꾼다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests -q`
기대: `603 + 8 = 611 passed` (Task 1 의 4개 + Task 2 의 4개), 4 skipped, 1 xfailed.

- [ ] **Step 5: mutation check**

`uv` 를 `np.nan` 대신 `float(full["uv"].sum())` 으로 바꾸면
`test_uv_is_nan_on_a_slice_rather_than_a_sum` 이 실패해야 한다.
`full_combination_rows(one, SESSION_AXES)` 를 `one` 으로 바꾸면
`test_a_segment_slice_still_gives_the_additive_measures` 가 400 대 200 으로 실패해야 한다.

- [ ] **Step 6: 실데이터 확인**

```python
# PYTHONPATH=. .venv/bin/python
from analytics.analyses.cubes import load_cube_set
from analytics.analyses.operators import compare, decompose
from analytics.metrics.load import load_releases
from data_layer.config import Config

cubes = load_cube_set(Config.from_env(),
                      dates=[f"2026-07-{d:02d}" for d in range(14, 29)],
                      services=["top", "media", "entertain", "sports",
                                "content_v", "search"],
                      state_dict_version="sd_2ab5ec25e750dda2",
                      cube_names=("session",))
c = compare(cubes.filter(service_type="MA"), "session_trend",
            on="app_version", a="9.5.1", b="9.5.0", released=load_releases())
print(c.dates_used, c.pooled, c.weight_skew)
print(c.per_day.to_string(index=False))
```

**이 숫자는 아직 아무도 본 적이 없다.** 나오는 값을 실행 보고에 적고,
`tests/analytics/analyses/test_analyses_on_real_cubes.py` 에 회귀 그물로 고정한다.
`weight_skew` 가 크면(0.5 이상) 합산을 그대로 읽지 말고 `decompose` 를 함께 낸다.

- [ ] **Step 7: 커밋**

```bash
git add analytics/analyses/operators.py analytics/analyses/descriptive.py \
        tests/analytics/analyses/test_compare_on_session_cubes.py \
        tests/analytics/analyses/test_session_trend.py \
        tests/analytics/analyses/test_analyses_on_real_cubes.py
git commit -m "feat: compare session-cube analyses without summing uv"
```

- [ ] **Step 8: SKILL.md 갱신**

`.claude/skills/basic-analysis/SKILL.md` 의 분석 표에서 `session_trend` 줄에 "세그먼트로
자르면 `uv` 는 NaN(봉투 경고)" 를 적고, "Common mistakes" 의 세션 큐브 비교 항목을
지운다(더 이상 사실이 아니다). `(period, app_version)` grouping set 이 필요한 것은
**`uv` 를 버전별로 볼 때만** 이라고 남긴다.

---

### Task 3: `screen_pair_affinity` — PMI 를 발행 가능하게

**왜:** `metrics.markov.pointwise_mutual_information` 은 있는데 이름 붙은 분석이 없어서
**발행되지 않는다**(이 층의 규칙: 발행하려면 분석으로 코드화한다). 쌍(from, to) 단위라
`screen_flow` 의 화면 한 줄 프레임에 못 들어간다. 얇은 셀 임계치는 **발명하지 않는다** —
프리미티브가 이미 `cnt` 를 함께 내므로 전부 내고 소비자가 거른다.

**Files:**
- Modify: `analytics/analyses/flow.py`
- Create: `tests/analytics/analyses/test_screen_pair_affinity.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
"""PMI 쌍 분석. headline 이 상호정보량인 것이 요점이다."""
import numpy as np
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis


def _cubes(rows) -> CubeSet:
    edges = pd.DataFrame([
        {"period": "2026-07-27", "from_state": f, "to_state": t, "cnt": c,
         "dur_n": c, "dur_sum": float(c) * 10.0}
        for f, t, c in rows
    ])
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


# 완전 결정적인 짝짓기: A는 항상 X로, B는 항상 Y로 간다.
# 그러면 현재 화면이 다음 화면을 완전히 결정하므로 상호정보량 = log(2) 다.
PAIRED = [("A", "X", 50), ("B", "Y", 50)]

# 완전 독립: A·B 가 각각 X·Y 로 반반 간다. 상호정보량 = 0.
INDEPENDENT = [("A", "X", 25), ("A", "Y", 25), ("B", "X", 25), ("B", "Y", 25)]


def test_one_row_per_observed_pair():
    got = get_analysis("screen_pair_affinity")(_cubes(PAIRED))
    assert len(got.frame) == 2
    assert {"from_state", "to_state", "cnt", "pmi"} <= set(got.frame.columns)


def test_the_rows_are_sorted_by_affinity():
    rows = [("A", "X", 50), ("A", "Y", 50), ("B", "Y", 1)]
    got = get_analysis("screen_pair_affinity")(_cubes(rows))
    assert got.frame["pmi"].is_monotonic_decreasing


def test_headline_mutual_information_is_zero_when_the_next_screen_is_independent():
    got = get_analysis("screen_pair_affinity")(_cubes(INDEPENDENT))
    assert got.headline["mutual_information"] == pytest.approx(0.0)


def test_headline_mutual_information_is_log_two_for_a_perfect_pairing():
    """현재 화면이 다음 화면을 완전히 결정하고 후보가 둘이면 log(2) 다."""
    got = get_analysis("screen_pair_affinity")(_cubes(PAIRED))
    assert got.headline["mutual_information"] == pytest.approx(np.log(2))


def test_headline_is_the_cnt_weighted_mean_of_pmi():
    """상호정보량 = Σ p(i,j)·PMI(i,j). 단순 평균이 아니라 물량 가중이다."""
    rows = [("A", "X", 90), ("A", "Y", 10), ("B", "Y", 100)]
    got = get_analysis("screen_pair_affinity")(_cubes(rows))
    weights = got.frame["cnt"] / got.frame["cnt"].sum()
    assert got.headline["mutual_information"] == pytest.approx(
        float((got.frame["pmi"] * weights).sum())
    )
    assert got.headline["pairs"] == 3


def test_thin_cells_are_flagged_because_their_pmi_spikes_hardest():
    rows = PAIRED + [("A", "Z", 1)]
    got = get_analysis("screen_pair_affinity")(_cubes(rows))
    assert [w["check_name"] for w in got.envelope["warnings"]] == [
        "thin_transition_cells"
    ]


def test_an_empty_transition_frame_raises_rather_than_returning_zeros():
    empty = CubeSet(session=None, transition=pd.DataFrame(
        columns=["period", "from_state", "to_state", "cnt", "dur_n", "dur_sum"]),
        quality=None, state_dict_version="sd_abc", services=["top"],
        requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="no transitions"):
        get_analysis("screen_pair_affinity")(empty)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/analyses/test_screen_pair_affinity.py -q`
기대: 전부 `UnknownAnalysisError: no analysis named 'screen_pair_affinity'`.

- [ ] **Step 3: 구현 — `flow.py` 끝에 추가**

```python
@analysis("screen_pair_affinity")
def screen_pair_affinity(cubes: CubeSet, **_) -> AnalysisResult:
    """전이 쌍의 **결합 강도**(PMI). 빈도 순위와 다른 질문에 답한다.

    PMI 는 "흔한 화면이라 흔한" 전이를 걸러낸다 — 카운트 1위가 PMI 1위가 아닌 것이
    이 지표의 존재 이유다. `screen_flow` 에 넣을 수 없는 이유는 쌍 단위라 화면 한 줄에
    안 들어가기 때문이고, 넣으려면 "어느 셀부터 믿을 만한가" 하는 임계치를 발명해야
    한다. **임계치를 만들지 않고 `cnt` 를 함께 낸다** — 얇은 셀의 PMI 가 가장 크게 튀므로
    소비자가 그 열을 보고 거른다.

    `headline` 의 `mutual_information` 은 `Σ p(i,j)·PMI(i,j)` 로, 곧 상호정보량
    I(현재 화면; 다음 화면) 이다(nats). "현재 화면을 알면 다음 화면을 얼마나 아는가" 이고,
    쌍마다 값이 다른 PMI 와 달리 세그먼트끼리 견줄 수 있는 스칼라다. 0 이면 다음 화면이
    현재와 독립이고, 완전히 결정적이며 후보가 둘이면 log(2) 다.

    **`START`·`EXIT` 쌍을 빼지 않는다.** `screen_communities` 는 그 둘이 모든 화면과
    이어져 군집을 뭉개므로 뺐지만, 여기서는 `START→X` 가 "어느 화면이 세션을 특징적으로
    시작하는가", `X→EXIT` 가 "어느 화면이 특징적으로 끝내는가" 라는 실제 질문에 답한다.
    상호정보량도 그 둘을 포함한 전이 분포 전체에 대한 값이라야 뜻이 온전하다.

    커버리지는 비운다 — 카운트만 쓰므로 부분 측정 문제가 없다. 체류 커버리지를 실으면
    쓰지도 않은 측정값의 신뢰도를 말하는 셈이다.
    """
    edges = cubes.transition
    if edges is None:
        raise ValueError("screen_pair_affinity needs the transition cube; it is absent")
    P = transition_matrix(edges)
    frame = pointwise_mutual_information(P).sort_values(
        "pmi", ascending=False, ignore_index=True
    )
    total = float(frame["cnt"].sum())
    weights = frame["cnt"] / total if total > 0 else 0.0
    return AnalysisResult(
        frame=frame,
        headline={
            "mutual_information": float((frame["pmi"] * weights).sum())
            if total > 0 else float("nan"),
            "pairs": float(len(frame)),
        },
        envelope=envelope_for(cubes, {}, _thin_cell_warning(edges)),
        viz={"kind": "heatmap", "x": "from_state"},
    )
```

`flow.py` 상단 임포트에 `pointwise_mutual_information` 을 추가한다. 파일 docstring 도
고친다 — 지금 "화면 한 줄로 합친다" 인데 이제 쌍 모양 분석도 들어 있다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests -q`
기대: Task 1·2 까지 했다면 `611 + 7 = 618 passed`.

`test_analyses_on_real_cubes.py::test_the_shipped_registry_is_what_it_should_be` 의
목록에 `screen_pair_affinity` 를 추가해야 한다 — **이 테스트가 실패하는 것이 정상이고,
분석이 추가된 것을 눈에 띄게 하려고 있는 테스트다.**

- [ ] **Step 5: mutation check**

가중치를 `weights` 대신 `1/len(frame)`(단순 평균)으로 바꾸면
`test_headline_is_the_cnt_weighted_mean_of_pmi` 와
`test_headline_mutual_information_is_log_two_for_a_perfect_pairing` 이 실패해야 한다.

- [ ] **Step 6: 실데이터 확인 후 커밋**

15일치로 돌려 상호정보량과 PMI 1위 쌍이 카운트 1위 쌍과 다른지 확인하고 보고에 적는다
(카운트 1위는 `top/엠탑조회` → 자기 자신인 자기 루프다).

```bash
git add analytics/analyses/flow.py \
        tests/analytics/analyses/test_screen_pair_affinity.py \
        tests/analytics/analyses/test_analyses_on_real_cubes.py
git commit -m "feat: add the screen_pair_affinity analysis over PMI"
```

- [ ] **Step 7: SKILL.md 갱신**

분석 표에 `screen_pair_affinity` 를 추가하고, "PMI 는 아직 이름 붙은 분석이 없다" 문단을
지운다. description frontmatter 의 PMI 언급은 그대로 둔다(이제 사실이다).

---

## 완료 기록 (2026-07-30, Task 1~3)

**Task 1~3 전부 완료.** 전체 스위트 **624 passed, 4 skipped, 1 xfailed** (11.6초).
분석 7개(`screen_pair_affinity` 추가)와 연산자 2개가 세션·전이 큐브 양쪽에 걸린다.
커밋: `b405742`(Task 1·2), `8d07ba7`(Task 3).

계획서가 예상한 611 대신 624 인 이유는 실큐브 회귀 테스트를 5개 더 넣었기 때문이다
(Task 2 의 가정을 실데이터로 검산한 것 4개 + PMI 1개). 계획서 본문은 당시 판단 기록으로
두고 고치지 않았으니 다음 사람은 이 절을 먼저 읽는다.

### 미검증이라고 표시한 가설 — 맞았다

**슬라이스에는 롤업 행이 없어 fallback 경로를 탄다**는 추론은 맞았다. 다만 **먼저 나는
예외는 `NonAdditiveMeasureError` 였다**(`KeyError: 'cnt'` 가 아니다) — `compare` 가
`weight_skew` 보다 분석을 먼저 돌리기 때문이다.

그리고 가산성을 **실큐브로 직접 검산했다**(계획서는 기존 metrics 테스트를 인용만 했다).
15일 전부 `sessions`·`pv`·`events`·`duration_sum` 은 `(period)` 롤업 행과 배율
**1.000000**, `uv` 만 **1.68~1.76배**다. 계획서가 적어 둔 "1.71배" 는 범위의 한 점이다.
이 검산이 `test_the_session_cube_is_additive_except_uv` 로 남아 있다.

### 계획서의 실패 기대가 틀린 곳

**Task 1 Step 4 의 "하나만 남아 실패한다" 는 틀렸다.** Task 1 만 끝낸 상태에서 네 테스트가
**전부** `NonAdditiveMeasureError` 로 실패한다 — `test_compare_on_session_cubes.py` 의 네
테스트가 다 `compare()` 를 거치고, `compare` 는 물량 컬럼을 만지기 전에 분석을 돌린다.
Task 1 단독으로는 어느 것도 통과시킬 수 없다. Step 2 의 "둘 다 해야 통과한다" 가 맞고
Step 4 가 그와 어긋났다.

### 계획서의 mutation check 가 반만 들은 곳

**Task 3 의 "단순 평균으로 바꾸면 `log(2)` 테스트도 실패한다" 는 틀렸다.** `PAIRED` 는
두 쌍의 `cnt` 가 똑같이 50 이라 물량 가중과 단순 평균이 **같은 값**을 낸다. 죽는 것은
`test_headline_is_the_cnt_weighted_mean_of_pmi` 하나이고, 그것도 프레임에서 가중치를 다시
계산하는 동어반복이라 절대값을 고정하지 못한다.

그래서 **90:10 결정적 짝짓기**를 추가했다: 가중 0.325083(= H(0.9, 0.1)) 대 단순 평균
1.203973 으로 갈린다. 결정적 짝짓기의 상호정보량이 현재 화면 분포의 엔트로피라는 성질을
쓰면 절대값이 고정된다. **대칭적인 픽스처는 가중을 검증하지 못한다** — 함정 8번과 같은
종류이고, 이번에는 잔차가 아니라 대칭성이 원인이다.

### 계획서가 지우라고 한 것이 없던 곳

Task 2 Step 8 의 "`Common mistakes` 의 세션 큐브 비교 항목을 지운다" — **그런 항목이
SKILL.md 에 없다.** 세션 큐브를 비교할 수 없다는 서술은 이전 계획서의 "남은 공백" 4번에만
있었다. 대신 분석 표 아래에 세션 큐브도 `compare` 에 걸린다는 단락을 새로 넣었다.

### 실데이터에서 처음 나온 숫자

**세션 큐브 버전 비교** (9.5.1 vs 9.5.0, MA, 배포일 이후 3일, `seconds_per_session`):
날짜별 **−43.7 / −11.5 / −7.2%**, 합산 **−18.8%**, `within −28.0%` / `between +9.2%`,
`weight_skew 0.51`. **같은 두 버전의 기대 걸음 수는 +4~7% 였다 — 두 지표가 반대로
움직인다.** 9.5.1 세션은 화면을 더 많이 밟으면서 더 짧게 머문다.

**그대로 인용하면 안 된다.** `within` −28.0% 는 거의 전부 07-26 에서 온다. 그날 9.5.1 은
56만 세션, 9.5.0 은 1,440만으로 **25:1** 이라 배포일 컷오프를 지나고도 램프업 첫날의 소수
집단을 재고 있다. 회귀 그물은 크기가 아니라 부호와 이 취약함(`b_cnt/a_cnt > 20`)을 고정한다.

**롤업 행의 부풀림은 픽스처보다 크다.** 손으로 만든 프레임은 2배인데 실큐브는 하루 단위
**정확히 8배**(grouping set 8개)이고, 15일치를 이어붙이면 **9.0배**다(파일마다 날짜까지
접은 `()` 행이 하나 더 있어 `period` NULL 행이 15개). SKILL.md 의 "about 9 times" 는
이어붙인 프레임 기준이라 맞다.

**PMI**: 상호정보량 **0.641 nats**, 251쌍, 0.15s. 얇은 셀 620,247개(18.91%).
**카운트 1위가 PMI 47위다** — `top/엠탑조회` 자기 루프(3억 120만, PMI 0.397). PMI 1위는
관측 **263건**짜리 `content_v/other` 자기 루프(12.16)이고, 상위 8쌍이 거의 `*/other`
자기 루프다. 하위권은 서비스를 건너뛰는 쌍(media↔top, media↔sports)으로 −11~−15.5 다.
`START`·`EXIT` 를 빼면 0.641 → **0.723 으로 오른다**(221쌍) — 빼지 않기로 한 것은 답할
질문 때문이고 값을 키우려는 게 아니다.

**`*/other` 가 PMI 상위를 채우는 것**은 새 관찰이다. 이름 없는 화면이 이름 없는 화면으로
이어지는 경향이 가장 강하다는 뜻이고, 아래 "따로 파볼 만한 것" 의 `page_name_ambiguous`
와 같은 곳을 가리킨다.

---

## 이 계획서가 끝난 뒤 남는 것

| | 무엇 | 선행 조건 |
|---|---|---|
| A4-full | 세션 큐브에 `(period, app_version)` grouping set 추가 → **`uv` 를 버전별로** 볼 수 있다 | `analytics/cube/sql.py` 수정 + 세션 큐브 15일 재빌드(≈1.3시간, Trino). `sql_hash` 가 바뀌어 세션 큐브만 다시 만들어진다. **`uv` 를 버전별로 봐야 할 요구가 실제로 생길 때만 한다** |
| B | 3단계 행동층 — `plans/2026-07-29-action-layer-phase3.md` Task 1~8 | Trino. **Task 1(화면 이름 공간 측정)이 Task 2·3 을 결정하고, 그래서 Task 5~8 본문이 의도적으로 비어 있다** — Task 1 을 끝낸 사람이 채운다. 분석 4개(`click_distribution`·`conditional_flow`·`path_ranking`·`markov_order_test`)가 여기 걸려 있다 |
| C | 4단계 대시보드 | 계획서 없음. 기술 미정(의도적). 설계는 "대시보드가 분석을 직접 호출 + 본 것 자동 발행" |
| D-1 | state 사전 채택 가중치가 이벤트 행 수라 봇에 노출된다 | 스펙 리스크 ①. 미해결 |
| D-2 | 마르코프 변형: 1차 가정 검정(`path` n=3) → 2차 → semi-Markov → HMM/VLMC | 뒤쪽은 큐브가 시퀀스를 집계해 버려 **지금 구조로 불가**. 시퀀스 캐시 설계가 선행 |
| D-3 | DiD(같은 사람 전후 비교) | 인과가 필요해질 때. 유저별 데이터를 로컬에 내리지 않고 서버에서 코호트×상대일로 집계 |
| D-4 | 큐브 날짜 확장 | D 빌드에 D+1 파티션이 필요하다. **2026-07-29 큐브는 07-30 부터** 만들 수 있다 |

**따로 파볼 만한 것:** `page_name_ambiguous` 가 `search` 69.6~79.3%, `sports`
27.1~35.3% 다. 그 두 서비스의 화면 이름 상당수가 여러 페이지를 가리키므로, 화면 단위
분석이 서로 다른 페이지를 한 이름에 섞고 있다. 임계치 문제가 아니라 사전 어휘 품질
문제이고, A/B/C/D 어디에도 안 들어간 항목이다.

## 이 층에서 특히 의심할 자리

1. **가드를 분석으로 흘리지 말 것.** 날짜 겹침·배포일 검사는 `compare` 한 곳에만 있다.
2. **`headline` 없는 분석을 만들지 말 것.** 연산자가 그 분석에만 안 걸린다.
3. **비율의 분자·분모를 프레임에 함께 낼 것.** 안 그러면 소비자가 headline 을 검산할 수
   없다(`session_trend` 의 `duration_sum`, PMI 의 `cnt`).
4. **모르는 것은 NaN 이다.** 0 으로 채우면 "0초 머물렀다" 와 "얼마나 머물렀는지 모른다"
   가 구분되지 않는다. `uv` 를 합산으로 때우지 않는 것도 같은 규칙이다.
5. **잔차로 정의된 값은 항등식으로 검증되지 않는다**(위 함정 8번).

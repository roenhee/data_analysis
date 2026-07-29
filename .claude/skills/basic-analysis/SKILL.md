---
name: basic-analysis
description: Use when someone wants full-population analytics on the data_analysis project — 기간별 UV/PV (unique visitors / page views), 세션 수, 체류시간(dwell time), 유저당 세션·체류, 화면 전이 마르코프 지표 (전이확률·이탈확률·stationary·기대 걸음 수·흡수확률·PMI·엔트로피·PageRank), 화면 군집, 도달 확률 — segmented by app_version / os / gender / age_band / daypart / service_type, and 세그먼트 비교(compare)·구성 분해(decompose). Reads pre-built local cubes; never queries Trino directly.
---

# Basic Analysis

## Overview

Compute full-population metrics from the **pre-built local cubes** in `cache/cubes/`,
then publish them through the ②↔③ result contract.

Two layers, and you work in the upper one:

| 층 | 무엇 | 누가 쓰나 |
|---|---|---|
| `analytics/metrics/` | 순수 프리미티브 (행렬·비율·커버리지) | 분석이 쓴다 |
| `analytics/analyses/` | **이름 붙은 분석 6개 + 연산자 2개** | 여기서 고른다 |

**Claude 는 계산하지 않는다.** 이름 붙은 분석을 고르고, 연산자를 걸고, 나온 숫자를
말로 해석한다. 탐색은 자유롭지만 **발행되지 않는다** — 발행하려면 분석으로 코드화한다.
그래야 대시보드와 Claude 가 같은 코드 경로를 지나 같은 답을 낸다. 노트북에서 손으로
계산한 값을 결론으로 쓰면 두 답이 갈리고, 어느 쪽이 맞는지 아무도 모른다.

계산 층은 Trino 를 모르고 **서버로 되돌아가지 않는다.** 날짜의 큐브가 없으면 답은
에러다, 조용히 작아진 숫자가 아니다.

## Prerequisite: the cubes must exist

    .venv/bin/python scripts/build_cubes.py <시작> <끝> <서비스,목록>

Building is expensive (~9 minutes per day across six services) and only happens once
per date; analysis afterwards runs locally in well under a second per analysis.
To append dates later,
reuse the dictionary that the build prints — otherwise the state dictionary version
changes, the cache key changes with it, and every earlier date rebuilds:

    .venv/bin/python scripts/build_cubes.py 2026-07-01 2026-07-13 top,media \
        --state-dict=sd_2ab5ec25e750dda2

## Definitions that trip people up

**세션 = `(user.uuid, user.suid)`**, attributed to its **first event's** date and axis
values. Not `(app_user_id, isuid)` — that was the old sampled schema.

**서비스는 축이 아니라 범위다.** 44.7% of sessions touch more than one service, so a
session cube built for `top,media` reports "sessions that used top **or** media" and
cannot be split back apart. For per-service session figures, build that service alone.
Transitions and quality are unaffected — transition states carry a `top/` prefix and
the quality cube keys on `service_code`.

**체류시간은 두 가지고 서로 다른 수치다.**

| 출처 | 정의 | 커버리지 |
|---|---|---|
| `session` 큐브 `duration_sum` | 세션 span (첫→마지막 이벤트, 초) | 100% |
| `transition` 큐브 `dur_sum` | `UsagePage` 행의 체류 합 | **57~69%** |

Every dwell result carries a `dwell_definition` column. Do not pool them.

**이탈 = 그 세션의 마지막 화면.** Not a timeout, not an explicit close event. Measured
over 14 days, 89.2% of app sessions carry an `AppExit` right after, but web has no such
signal at all, so for web this means only "the log stopped". `service_type` is an axis —
split MA / MW / PW before quoting an exit rate.

**버전 비교는 겹치는 날짜 위에서만.** App versions roll out in stages, so two versions
normally do **not** occupy the same range of dates — 9.5.0 ran 2%→91% over eleven days
before 9.5.1 appeared at all. Comparing across the full window measures the calendar:
expected steps read **+2.9%** that way against **−0.2%** on the shared dates, sign
included. Always route a version delta through `compare.restrict_to_comparable`, which
refuses a disjoint pair outright.

**`period` 는 귀속일이다.** The date the session started, matching the file's `date=`
partition. It is not the `date_id` the first event was written to — those disagree on
0.09% of sessions, skewed toward D+1, because events near midnight land in the next
partition.

## 이름 붙은 분석

`list_analyses()` 가 목록이고, `get_analysis(name)` 이 함수다. 다른 데서 숫자를 만들지
않는다. 모든 분석은 `CubeSet` 하나를 받아 `AnalysisResult`(프레임 + `headline` 스칼라 +
봉투)를 낸다.

| 이름 | 큐브 | 프레임 | `headline` | 파라미터 |
|---|---|---|---|---|
| `session_trend` | session | 날짜별 UV·PV·세션·체류 | `sessions`·`pv_per_session`·`seconds_per_session` | `holidays` |
| `screen_dwell_rank` | transition | 화면별 방문당 체류 순위 | `mean_seconds_per_visit`·`dwell_coverage` | `warn_below` |
| `screen_flow` | transition | 화면별 이탈·정상분포·기대 걸음 수·엔트로피·PageRank | `mean_expected_steps`·`mean_exit_prob` | `exit_within`·`damping` |
| `reachability` | transition | k 걸음 안에 목표 화면에 닿을 확률 곡선 | `p_hit_within_{max_k}` | `source`·`target`·`max_k` **(필수)** |
| `screen_communities` | transition | 화면 군집 (Louvain) | `communities`·`modularity` | `seed`·`resolution` |
| `quality_report` | quality | 검사별·날짜별 위반 비율 | `worst_{검사}`·`exit_corroboration` | `thresholds` |

`headline` 이 있어야 연산자가 걸린다. 새 분석을 만들 때 `headline` 을 비우면 그 분석만
비교에서 빠진다.

**PMI 는 아직 이름 붙은 분석이 없다.** `metrics.markov.pointwise_mutual_information` 은
있지만 쌍(from, to) 단위라 화면 한 줄짜리 프레임에 안 들어간다 — 넣으려면 "어느 셀부터
믿을 만한가" 하는 임계치를 발명해야 하고, 하필 얇은 셀의 PMI 가 가장 크게 튄다(실측 엣지
셀 cnt 중앙값 9, 18.9% 가 1). 쌍 모양의 분석을 따로 만들 때까지 PMI 는 탐색용이고
**발행되지 않는다.**

### 실측 규모 (15일치 · 전이 3,279,905 / 세션 214,668 / 품질 251,822 행)

| 분석 | 프레임 | 소요 | 대표값 |
|---|---|---|---|
| `session_trend` | 15행 × 11열 | 0.14s | 세션 4.91억, 세션당 PV 8.0, 체류 556.6초 |
| `screen_dwell_rank` | 15행 × 6열 | 0.24s | 방문당 48.4초, 커버리지 56.5% |
| `screen_flow` | 15행 × 15열 | 0.32s | 기대 걸음 수 10.62, 이탈확률 9.75% |
| `screen_communities` | 15행 × 4열 | 0.48s | 군집 3개, modularity 0.394 |
| `quality_report` | 120행 × 5열 | 0.36s | 이탈 뒷받침 89.2%, 화면 커버리지 78.0% |
| `compare` (15일, 두 세그먼트) | — | 5.8s | 날짜별로 분석을 다시 돌리므로 가장 비싸다 |

화면이 15개뿐이라 프레임이 작다. 비용은 프레임 크기가 아니라 **큐브 행 수**에서 온다.

## 연산자 — 가드가 모여 있는 곳

비교는 분석의 종류가 아니라 **분석에 거는 연산**이다. 그래서 날짜 겹침·배포일 가드가
`compare` 한 곳에만 있고 분석 전부에 걸린다. 분석 안에 가드를 복사하면 반드시 갈라진다.

```python
# PYTHONPATH=. .venv/bin/python this_script.py
from analytics.analyses import get_analysis, list_analyses, publish
from analytics.analyses.cubes import load_cube_set
from analytics.analyses.operators import compare, decompose
from analytics.metrics.load import load_holidays, load_releases
from data_layer.config import Config

config = Config.from_env()

# 캐시 키는 로더가 빌더와 같은 함수로 유도한다 — `sql_hash` 는 큐브마다 다르고
# 사전·서비스·테이블 좌표까지 들어가서 손으로 채울 수 있는 값이 아니다.
# 부분 빌드는 기본적으로 거부한다(`require_complete=False` 로 일부러 볼 수 있다).
cubes = load_cube_set(
    config,
    dates=["2026-07-26", "2026-07-27", "2026-07-28"],
    services=["top", "media"],           # 축이 아니라 빌드 범위다
    state_dict_version="sd_2ab5ec25e750dda2",
    cube_names=("session", "transition"),   # 필요한 큐브만 — 기본은 셋 다
)

holidays, _ = load_holidays()
trend = get_analysis("session_trend")(cubes, holidays=holidays)
flow = get_analysis("screen_flow")(cubes.filter(service_type="MA"), exit_within=(1, 3))

# 버전 비교 — 겹치는 날짜와 배포일 컷오프가 자동으로 걸린다
c = compare(cubes.filter(service_type="MA"), "screen_flow",
            on="app_version", a="9.5.1", b="9.5.0", released=load_releases())
c.pooled            # 합산 델타 — 이것만 보면 안 된다
c.per_day           # 날짜별 델타
c.sign_disagrees    # 날짜별과 합산의 부호가 갈리는가
c.weight_skew       # 두 세그먼트의 날짜 가중치 어긋남 (0이면 같은 분포)

# 합산이 날짜별과 다르면 분해한다
d = decompose(cubes.filter(service_type="MA"), c, by=["period"],
              metric="mean_expected_steps")
d.within            # 층 안 효과 = 구성이 b 와 같았다면의 델타
d.between           # 구성 변화가 만든 몫 (within + between == pooled)
d.composition       # 축별 구성 어긋남 (총변동거리)

publish(config, flow, run_id="r1", analysis_type="screen_flow", title="MA 화면 흐름")
```

`publish` 는 봉투 필수 항목이 하나라도 없으면 **거부한다**. 분석이 자기 봉투를 만들므로
나중에 채우려 하지 말 것.

## 합산 델타 하나만 읽지 말 것 — 실측

9.5.1 vs 9.5.0, `service_type=MA`, 배포일 이후 3일, `mean_expected_steps`:

| | 값 |
|---|---|
| 날짜별 (07-26/27/28) | **+9.2% / +4.5% / +6.8%** |
| 합산 | **+0.71%** |
| `within` (층 안 효과) | **+7.5%** |
| `between` (구성 변화) | **−6.8%** |
| `weight_skew` | 0.58 |

합산만 보면 "효과 없음"이라고 결론낸다. 하루도 +4.5% 아래가 없는데도 그렇다 — 9.5.1 은
전이의 대부분이 07-28 에, 9.5.0 은 07-26 에 몰려 있어서 각 버전이 자기가 몰린 날의 기저
수준을 물고 온다. `decompose` 가 그 몫을 `between` 으로 떼어낸다.

대조군: 성별 비교(F vs M)는 15일 내내 −26.1%~−21.0% 로 부호가 안 바뀌고 `weight_skew`
0.009 다. 성별은 날짜에 고루 퍼져 있어 합산이 날짜별과 같은 자리에 있다.

## Rules that are enforced in code

- **`require_complete()` before any ratio, mean, or probability.** `read_cube` returns
  whatever dates exist; asking for 30 days and getting 3 otherwise yields a plausible
  number with the wrong denominator and no signal.
- **Never sum `uv`.** It is not additive — on a real cube, summing overstates it by
  1.71x. `additive_sum` refuses it; read the cube's rollup row instead.
- **Never sum the session cube raw.** It holds `GROUPING SETS` rollup rows in the same
  file, and summing counts each session about 9 times. Go through
  `full_combination_rows` or `rollup_rows`.
- **Screen dwell divides by `dur_n`, not `cnt`.** Dividing by `cnt` deflates the mean by
  exactly the coverage ratio.
- **Route version deltas through `compare`.** It calls `comparable_dates` for you and
  refuses a disjoint pair outright. A delta across disjoint date windows measures the
  rollout schedule, not the version. Pass `released=load_releases()` too — 배포 전
  트래픽은 적은 표본이 아니라 다른 모집단(테스터)이다. 실측에서 배포 전 이틀을 넣으면
  하루 델타가 −80.4% 까지 튀고 합산이 +0.71% 에서 +2.9% 로 바뀐다.
- **`publish` 는 봉투 없이는 거부한다.** 커버리지와 state 사전 버전이 없는 결과는
  전수처럼 읽힌다.
- **Never read rollups from a multi-day frame.** Each cube file carries its own rollup
  rows, so concatenating days then reading a rollup returns several rows for one
  coordinate; summing them silently multiplies. `rollup_rows` raises instead.
- **Attach an `Envelope`.** Coverage, quality warnings, the state dictionary version,
  the service scope, and which dates were actually read.

## Common mistakes

- Expecting the metrics layer to fetch from Trino when a cube is missing. It will not —
  build the cube.
- Summing daily UV to get monthly UV. Read the rollup row for the coarser grain instead.
- Comparing dwell across services, OS families, or distant app versions. Coverage varies
  (search 0%, top web 65.6%, top android 84.8%), so only compare where coverage matches.
  Adjacent versions differ by 0.4pp and are safe.
- Quoting one exit rate across app and web. They mean different things.
- Reading `expected_steps_to_exit` as always finite. States that can fall into somewhere
  with no route to EXIT are reported `inf`, and that is the correct answer — and
  `screen_flow` lets it reach the `headline` on purpose.
- Quoting `screen_communities`' community **count** as a finding. 실측 15일치는 화면이
  15개뿐이고 modularity 0.394 라, 노드 순서만 다른 같은 그래프에서 4개(Q=0.395878) 와
  3개(Q=0.394087) 가 나왔다. 어느 화면들이 함께 묶이는 경향인지는 읽을 수 있지만
  "군집이 정확히 N개" 는 이 데이터가 답할 질문이 아니다.
- Reading a `quality_report` warning as being about one app version. 경고는 **버전을
  접은 (검사, 서비스, 날짜)** 비율이다 — 임계치의 근거가 집계된 비율이라 같은 수준에서
  잰다. 그래서 한 버전만 망가진 경우는 그 서비스의 일별 숫자에 희석된다. 버전 질문은
  `cubes.filter(app_version=...)` 로 따로 묻는다.
- Passing the busiest screen pair to `reachability`. 실측에서 가장 굵은 쌍은
  `top/엠탑조회` → 자기 자신인 자기 루프이고, `reachability` 가 거부한다.
- Hand-assembling a `CubeSet`. Use `load_cube_set`. Filling `present_dates` with the
  requested dates claims a partial build is complete, and no exception is raised.
- Missing `PYTHONPATH=.` on a standalone script → `ModuleNotFoundError`.

## Engine (backend)

`analytics/analyses/` — `base.py` (`CubeSet`·`AnalysisResult`·`publish`·레지스트리),
`cubes.py` (`load_cube_set` — 이 층에서 파일시스템을 아는 유일한 모듈),
`operators.py` (`compare`·`decompose`), `descriptive.py`, `flow.py`, `quality.py`,
`communities.py` (`networkx`).

`analytics/metrics/` — `load.py` (cube loading, partial-build detection; the only module
here that touches the filesystem), `frame.py` (rollup rows, segment filters, additivity
guard), `markov.py`, `descriptive.py`, `coverage.py`, `calendar.py`, `compare.py`,
`envelope.py`.

Shipped config: `examples/config/holidays_kr.json`, `releases.json`,
`quality_thresholds.json` (임계치 7개 + 근거가 파일 안에 `basis` 로 있다. 규칙은
"관측 최댓값 위(드리프트) 아니면 나쁜 무리 최솟값 아래(상시 표시), 그 사이는 안 됨").

**실측 상시 경고 4건** — 지금 데이터가 이미 걸리는 것들이다: `search` 체류 계측 없음(100%),
`top` 세션 중 화면 없는 것 19.6~32.6%, `search`·`sports` 화면 이름 모호(70~79% / 27~35%).
마지막 것은 그 두 서비스의 화면 단위 해석이 서로 다른 페이지를 한 이름에 섞고 있다는 뜻이다.

Cubes come from `analytics/cube/` and `scripts/build_cubes.py`.
Design: `docs/superpowers/specs/2026-07-28-segmented-analytics-design.md`,
`docs/superpowers/specs/2026-07-29-skill-platform-shape-design.md`.
Plan: `docs/superpowers/plans/2026-07-29-metrics-phase2.md`,
`docs/superpowers/plans/2026-07-29-analyses-layer.md`.

---
name: basic-analysis
description: Use when someone wants full-population analytics on the data_analysis project — 기간별 UV/PV (unique visitors / page views), 세션 수, 체류시간(dwell time), 유저당 세션·체류, and 화면 전이 마르코프 지표 (전이확률·이탈확률·stationary·기대 걸음 수·흡수확률·PMI) — segmented by app_version / os / gender / age_band / daypart / service_type. Reads pre-built local cubes; never queries Trino directly.
---

# Basic Analysis

## Overview

Compute full-population descriptive and markov metrics from the **pre-built local
cubes** in `cache/cubes/`, then publish them through the ②↔③ result contract.

The calculation layer is `analytics/metrics/` — pure functions over cube DataFrames.
It does not know about Trino, and **it never falls back to the server.** If the cube
for a date is missing, the answer is an error, not a quietly smaller number.

## Prerequisite: the cubes must exist

    .venv/bin/python scripts/build_cubes.py <시작> <끝> <서비스,목록>

Building is expensive (~9 minutes per day across six services) and only happens once
per date; analysis afterwards runs locally in milliseconds. To append dates later,
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

## Recipe

```python
# PYTHONPATH=. .venv/bin/python this_script.py
from analytics.metrics import load_cube
from analytics.metrics.descriptive import engagement, screen_dwell, uv_pv
from analytics.metrics.compare import restrict_to_comparable
from analytics.metrics.envelope import Envelope, quality_warnings
from analytics.metrics.frame import select_segment
from analytics.metrics.markov import (
    absorption_probabilities, exit_probabilities, expected_steps_to_exit,
    pointwise_mutual_information, stationary_distribution, transition_matrix,
)
from data_layer.config import Config

config = Config.from_env()
dates = ["2026-07-26", "2026-07-27"]
key = dict(source_version=..., state_dict_version=..., axes=..., sql_hash=...)

sessions = load_cube(config, dates=dates, cube_name="session", **key).require_complete()
edges = load_cube(config, dates=dates, cube_name="transition", **key).require_complete()

# 기술통계 — folded 축은 큐브의 롤업 행에서 읽는다
uv_pv(sessions.frame, folded=("os", "gender", "age_band", "daypart"))
engagement(sessions.frame, folded=("os", "gender", "age_band", "daypart"))

# 버전 비교 — 두 버전이 함께 존재하는 날짜로 먼저 좁힌다
pair = restrict_to_comparable(edges.frame, "app_version", "9.5.1", "9.5.0")

# 마르코프 — 세그먼트를 먼저 좁히고 행렬을 만든다
seg = select_segment(pair, app_version="9.5.1", service_type="MA")
P = transition_matrix(seg)
exit_probabilities(P)
stationary_distribution(P)
expected_steps_to_exit(P)
absorption_probabilities(P)              # 기본 흡수 상태는 EXIT
pointwise_mutual_information(P)
screen_dwell(seg)                        # dur_sum / dur_n + 커버리지

envelope = Envelope.for_cube(edges, state_dict_version=..., services=["top", "media"])
```

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
- **Route version deltas through `restrict_to_comparable`.** A delta across disjoint
  date windows measures the rollout schedule, not the version, and the sign can flip.
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
  with no route to EXIT are reported `inf`, and that is the correct answer.
- Missing `PYTHONPATH=.` on a standalone script → `ModuleNotFoundError`.

## Engine (backend)

`analytics/metrics/` — `load.py` (cube loading, partial-build detection; the only module
here that touches the filesystem), `frame.py` (rollup rows, segment filters, additivity
guard), `markov.py`, `descriptive.py`, `envelope.py`.

Cubes come from `analytics/cube/` and `scripts/build_cubes.py`.
Design: `docs/superpowers/specs/2026-07-28-segmented-analytics-design.md`.
Plan: `docs/superpowers/plans/2026-07-29-metrics-phase2.md`.

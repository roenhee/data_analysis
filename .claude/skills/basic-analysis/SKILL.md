---
name: basic-analysis
description: Use when someone wants absolute (full-population) descriptive metrics on the data_analysis project — 기간별 UV/PV (unique visitors / page views), 세션 수, 체류시간(dwell time), 유저당 세션·체류 — optionally split by app_version / os / service_code, published via the result contract for the platform to render. Not for markov/sequence or sampled analyses.
---

# Basic Analysis

## Overview

Run **on-demand, absolute (full-population, non-sampled)** descriptive metrics on this project's event data and publish them through the ②↔③ result contract. This skill is a thin orchestration layer over the tested Python engine in `skills/descriptive/`: you pick the analysis + params, the engine builds the server-side aggregate SQL (Trino), runs it, shapes the result, and publishes it.

Separate from markov/sequence analyses. Absolute metrics come from a **server-side full-population aggregate**, not the sampled event cache — so the platform can trust them as real headline numbers.

## When to use

- User wants period **UV / PV** (순방문자 / 페이지뷰), **세션 수**, **체류시간**, or **유저당** 세션·체류, over a date window.
- Optionally **split by** app version, OS, or service.
- Results should be **published** so the platform (③) can render them.

**Not for:** markov / transition / sequence analysis; sampled analyses; arbitrary metric×dimension combos (the menu is fixed — extend the engine first if you need more).

## The menu (fixed)

| `analysis_type` | output columns |
|---|---|
| `uv_pv_by_period` | `period, <breakdown…>, uv, pv` |
| `session_engagement_by_period` | `period, <breakdown…>, sessions, total_duration, avg_duration_per_session, sessions_per_user, duration_per_user` |

**params** (a single dict):
- `window`: `[start, end]` ISO dates, both inclusive.
- `grain`: `"day" | "week" | "month"` (default `"day"`). UV and sessions are **non-additive** — each grain re-aggregates from raw; never sum a finer grain into a coarser one.
- `breakdown`: subset of `["app_version", "os", "service_code"]` (default none). Stacked **on top of** the always-present `period` axis.
- `filters`: `{column: value}` equality on that same whitelist (optional).

Definitions: a **session** = `(app_user_id, isuid)`. **체류시간** = session span (first→last event, seconds), and each session is attributed to its **first event's** period + breakdown value.

## Recipe

Run standalone driver scripts with `PYTHONPATH=.` from the repo root (only pytest gets the path for free, via `pytest.ini`). Real runs need `TIARA_ID` / `TIARA_PW` env vars for Trino. **Offline / no creds:** inject `aggregate_fetcher=` — a function `(config, source, sql) -> DataFrame` returning rows shaped like the SELECT — exactly as `tests/test_descriptive_run.py` does.

```python
# PYTHONPATH=. .venv/bin/python this_script.py
from data_layer.config import Config
from data_layer.config_artifacts import events_source_from_json, load_dictionary, config_version
from data_layer.results import read_result
from skills.descriptive.run import run_analysis
from skills.descriptive.descriptor import register

config = Config.from_env()                        # cache/ by default (gitignored)
source = events_source_from_json("examples/config/sources.json", "events")
register(config)                                  # (optional) list this skill in ③'s catalog

# config_version tags the result with the dictionary + sessionization it was built under.
# Sessionization convention for this skill is {"method": "isuid"} — use it so results stay comparable.
cv = config_version(load_dictionary("examples/config/dictionary.example.json"),
                    {"method": "isuid"})

rid = run_analysis(
    config, source,
    "uv_pv_by_period",
    params={"window": ["2026-01-05", "2026-01-06"], "grain": "day",
            "breakdown": ["app_version"]},
    run_id="jan-first-week",        # groups results produced in one session
    config_version=cv,
    # aggregate_fetcher=my_fake,    # ONLY when offline / no Trino creds
)

df, envelope = read_result(config, rid)           # what the platform reads back
```

When offline, the injected `aggregate_fetcher` returns rows shaped like the SELECT (columns = the menu table). For this `uv_pv_by_period` + `app_version` run:

```python
import pandas as pd
def my_fake(config, source, sql):
    return pd.DataFrame({"period": ["2026-01-05", "2026-01-05", "2026-01-06"],
                         "app_version": ["10.5.0", "10.6.0", "10.6.0"],
                         "uv": [1200, 340, 1500], "pv": [4300, 900, 5200]})
```

**Publishing is internal:** `run_analysis` returns an **id** and, as a side effect, writes `cache/results/<id>.parquet` (data) + `<id>.json` (envelope: `columns`, `viz` hints, `caveats`) and indexes `cache/manifest.json["published"]`. That file handoff **is** the ②→③ contract — the platform consumes it via `list_results` / `read_result`. Because these are full-population numbers, the envelope carries `caveats="전수집계(비샘플)"`.

To publish several results in one run, give each a distinct `params["title"]` (or vary the params) — the id is derived from `(run_id, analysis_type, title)`, and title defaults to a param-derived string, so identical params are idempotent and different params never overwrite each other.

## Common mistakes

- **`run_id` and `config_version` are separate required arguments**, NOT keys inside `params`.
- Putting `window` / `grain` / `breakdown` at the top level — they go **inside** `params`.
- Inventing your own `config_version` sessionization dict — use `{"method": "isuid"}`.
- Expecting a table back — `run_analysis` returns an **id**; the data is published to `cache/results/`.
- Missing `PYTHONPATH=.` on a standalone script → `ModuleNotFoundError: No module named 'data_layer'`.
- Summing daily UV to get monthly UV — re-run with `grain="month"` instead (UV is non-additive).
- Asking for a metric or breakdown dimension not in the fixed menu — add it to the engine (`skills/descriptive/`) first, with tests.

## Engine (backend)

The logic lives in `skills/descriptive/` — `sql.py` (aggregate SQL builders), `run.py` (`run_analysis`: validation, dispatch, shaping, publish), `descriptor.py` (catalog entry) — on top of the generic primitive `data_layer/fetch_aggregate.py`. Full design: `docs/superpowers/specs/2026-07-23-descriptive-analytics-design.md`.

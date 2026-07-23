from __future__ import annotations

import pandas as pd

from data_layer.config import Config
from data_layer.fetch_aggregate import fetch_aggregate
from data_layer.results import publish_result
from data_layer.sources import SourceDef
from skills.descriptive.sql import (
    BREAKDOWN_WHITELIST,
    build_session_engagement_sql,
    build_uv_pv_sql,
)

MENU = ("uv_pv_by_period", "session_engagement_by_period")
GRAINS = ("day", "week", "month")


def _validate(source: SourceDef, analysis_type: str, grain: str, breakdown: list, filters: dict) -> None:
    if analysis_type not in MENU:
        raise ValueError(f"unknown analysis_type {analysis_type!r}; valid: {list(MENU)}")
    if grain not in GRAINS:
        raise ValueError(f"unknown grain {grain!r}; valid: {list(GRAINS)}")
    for dim in list(breakdown) + list(filters):
        if dim not in BREAKDOWN_WHITELIST:
            raise ValueError(f"{dim!r} not in breakdown whitelist {list(BREAKDOWN_WHITELIST)}")
        if dim not in source.column_map:
            raise ValueError(f"{dim!r} not mapped in source.column_map")


def _shape_uv_pv(raw: pd.DataFrame, breakdown: list) -> tuple[pd.DataFrame, dict]:
    viz = {
        "chart_type": "line",
        "encoding": {
            "x": "period",
            "y": ["uv", "pv"],
            "series": breakdown[0] if breakdown else None,
        },
    }
    return raw, viz


def _shape_session_engagement(raw: pd.DataFrame, breakdown: list) -> tuple[pd.DataFrame, dict]:
    df = raw.copy()
    sessions, uv, dur = df["sessions"], df["uv"], df["total_duration"]
    df["avg_duration_per_session"] = (dur / sessions).where(sessions > 0)
    df["sessions_per_user"] = (sessions / uv).where(uv > 0)
    df["duration_per_user"] = (dur / uv).where(uv > 0)
    df = df.drop(columns=["uv"])
    viz = {
        "chart_type": "line",
        "encoding": {
            "x": "period",
            "y": ["sessions", "sessions_per_user"],
            "series": breakdown[0] if breakdown else None,
        },
    }
    return df, viz


_BUILDERS = {
    "uv_pv_by_period": build_uv_pv_sql,
    "session_engagement_by_period": build_session_engagement_sql,
}
_SHAPERS = {
    "uv_pv_by_period": _shape_uv_pv,
    "session_engagement_by_period": _shape_session_engagement,
}


def _default_title(analysis_type: str, grain: str, breakdown: list, filters: dict, window) -> str:
    parts = [analysis_type, grain]
    if breakdown:
        parts.append("by=" + "+".join(breakdown))
    if filters:
        parts.append("where=" + ",".join(f"{k}={v}" for k, v in sorted(filters.items())))
    parts.append(f"{window[0]}~{window[1]}")
    return " · ".join(parts)


def run_analysis(config: Config, source: SourceDef, analysis_type: str, params: dict, run_id: str, config_version: str,
                 aggregate_fetcher=None) -> str:
    """명명 지표를 파라미터로 요청받아 전수 집계 → shaping → publish_result.

    aggregate_fetcher(config, source, sql) -> DataFrame: 서버 fetch seam(테스트 주입).
    한 run에서 결과를 구분하려면 params["title"]을 다르게 준다(id가 결정적이므로).
    """
    grain = params.get("grain", "day")
    breakdown = params.get("breakdown", [])
    filters = params.get("filters", {})
    _validate(source, analysis_type, grain, breakdown, filters)

    window = params.get("window")
    if window is None:
        raise ValueError("params['window'] is required")

    sql = _BUILDERS[analysis_type](source, window, grain, breakdown, filters)
    raw = (aggregate_fetcher or fetch_aggregate)(config, source, sql)

    data, viz = _SHAPERS[analysis_type](raw, breakdown)
    caveats = "전수집계(비샘플)"
    if len(data) == 0:
        caveats += " · no data in window"

    title = params.get("title") or _default_title(analysis_type, grain, breakdown, filters, window)
    return publish_result(
        config, run_id=run_id, skill="descriptive",
        analysis_type=analysis_type, title=title,
        data=data, viz=viz, params=params, config_version=config_version,
        caveats=caveats,
    )

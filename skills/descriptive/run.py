from __future__ import annotations

from data_layer.fetch_aggregate import fetch_aggregate
from data_layer.results import publish_result
from skills.descriptive.sql import (
    BREAKDOWN_WHITELIST,
    build_uv_pv_sql,
)

MENU = ("uv_pv_by_period", "session_engagement_by_period")
GRAINS = ("day", "week", "month")


def _validate(source, analysis_type, grain, breakdown, filters):
    if analysis_type not in MENU:
        raise ValueError(f"unknown analysis_type {analysis_type!r}; valid: {list(MENU)}")
    if grain not in GRAINS:
        raise ValueError(f"unknown grain {grain!r}; valid: {list(GRAINS)}")
    for dim in list(breakdown) + list(filters):
        if dim not in BREAKDOWN_WHITELIST:
            raise ValueError(f"{dim!r} not in breakdown whitelist {list(BREAKDOWN_WHITELIST)}")
        if dim not in source.column_map:
            raise ValueError(f"{dim!r} not mapped in source.column_map")


def _shape_uv_pv(raw, breakdown):
    viz = {
        "chart_type": "line",
        "encoding": {
            "x": "period",
            "y": ["uv", "pv"],
            "series": breakdown[0] if breakdown else None,
        },
    }
    return raw, viz


_BUILDERS = {"uv_pv_by_period": build_uv_pv_sql}
_SHAPERS = {"uv_pv_by_period": _shape_uv_pv}


def run_analysis(config, source, analysis_type, params, run_id, config_version,
                 aggregate_fetcher=None):
    """명명 지표를 파라미터로 요청받아 전수 집계 → shaping → publish_result.

    aggregate_fetcher(config, source, sql) -> DataFrame: 서버 fetch seam(테스트 주입).
    한 run에서 결과를 구분하려면 params["title"]을 다르게 준다(id가 결정적이므로).
    """
    grain = params.get("grain", "day")
    breakdown = params.get("breakdown", [])
    filters = params.get("filters", {})
    _validate(source, analysis_type, grain, breakdown, filters)

    sql = _BUILDERS[analysis_type](source, params["window"], grain, breakdown, filters)
    raw = (aggregate_fetcher or fetch_aggregate)(config, source, sql)

    data, viz = _SHAPERS[analysis_type](raw, breakdown)
    caveats = "전수집계(비샘플)"
    if len(data) == 0:
        caveats += " · no data in window"

    return publish_result(
        config, run_id=run_id, skill="descriptive",
        analysis_type=analysis_type, title=params.get("title", analysis_type),
        data=data, viz=viz, params=params, config_version=config_version,
        caveats=caveats,
    )

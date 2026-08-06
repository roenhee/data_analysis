"""AnalysisResult → JSON. viz 를 Vega-Lite 스펙으로.

숫자는 만들지 않는다 — get_analysis 결과를 프론트가 먹을 JSON 으로 바꿀 뿐이다.
charts.py 의 Altair 는 이미 Vega-Lite 생성기라 .to_dict() 로 스펙을 얻는다.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from analytics.analyses.base import AnalysisResult, get_analysis
from dashboard import charts, filters, glossary, params, render
from api import cube_store

CHART_TOP = 20   # 차트에 그릴 상위 개수(막대 수천 개 방지). 표는 전량.


def _json_safe(value):
    """numpy/NaN/inf 를 JSON 안전 값으로. 표준 json 은 numpy 를 못 낸다."""
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def vega_spec(result: AnalysisResult, chart_top: int = CHART_TOP):
    """viz.kind → Vega-Lite dict. graph 는 별도 형태, 지원 안 하면 None(표만)."""
    viz = result.viz or {}
    frame = result.frame
    if viz.get("kind") == "graph":
        # 1단계 골격엔 graph 분석이 없다(session_trend=line). 형태만 유지.
        return {"kind": "graph", "x": viz.get("x", "state"),
                "edges": viz.get("edges", [])}
    kind = charts.chart_kind(viz)
    x = viz.get("x")
    if kind == "line" and x in frame.columns:
        return charts.line_chart(frame, x).to_dict()
    if kind == "bar" and x in frame.columns:
        y = next((c for c in frame.columns
                  if pd.api.types.is_numeric_dtype(frame[c])), None)
        if y:
            return charts.bar_chart(frame, x, y, chart_top).to_dict()
    if kind == "heatmap":
        to = "to_state" if "to_state" in frame.columns else "to_service"
        return charts.heatmap_chart(frame, x, to, viz.get("value", "cnt")).to_dict()
    return None


def result_to_json(result: AnalysisResult, period_days_value: int | None = None) -> dict:
    """AnalysisResult → {headline, columns, rows, viz, envelope}."""
    cards = render.headline_cards(result.headline)
    headline = [
        {"label": glossary.metric_label(key), "value": shown,
         "help": glossary.metric_help(key) or None}
        for key, shown in cards
    ]
    columns = [
        {"key": c, "label": glossary.column_label(c),
         "help": glossary.column_help(c) or None}
        for c in result.frame.columns
    ]
    rows = [[_json_safe(v) for v in row]
            for row in result.frame.to_numpy().tolist()]

    env = render.envelope_summary(result.envelope)
    warnings = [glossary.warning_label(w) for w in env["warnings"]]
    if period_days_value is not None and period_days_value > cube_store.SOFT_LIMIT_DAYS:
        warnings.append("기간이 한 달을 넘어 느릴 수 있습니다")
    envelope = {
        "warnings": warnings,
        "state_dict_version": env["state_dict_version"],
        "n_dates": env["n_dates"],
        "period_days": period_days_value,
    }
    return {"headline": headline, "columns": columns, "rows": rows,
            "viz": vega_spec(result), "envelope": envelope}


def run_analysis(name: str, start: str, end: str, segment: dict,
                 param_values: dict, state_dict_version: str) -> dict:
    """cube_store 로드 → 축 필터 → coerce → 분석 호출 → JSON."""
    cubes = cube_store.load(
        tuple(sorted(filters.cube_names_for(name))),
        start, end, tuple(segment["services"]), state_dict_version,
    )
    cubes = filters.apply_segment(cubes, segment)
    call_params = params.coerce(name, param_values)
    result = get_analysis(name)(cubes, **call_params)
    return result_to_json(result, period_days_value=cube_store.period_days(start, end))

"""viz.kind → 차트 데이터 준비. 순수 — st.* 호출 없음.

app.py 가 반환값을 st.bar_chart / st.line_chart / st.dataframe 에 넘긴다. graph 는 이
계획서에서 표로 대체하므로 chart_kind 가 "table" 로 떨어뜨린다.
"""
from __future__ import annotations

import pandas as pd

_SUPPORTED = {"bar", "line", "heatmap"}


def chart_kind(viz: dict) -> str:
    """그릴 차트 종류. 지원 안 하는 kind(graph 등)는 표로."""
    kind = viz.get("kind", "table")
    return kind if kind in _SUPPORTED else "table"


def bar_data(frame: pd.DataFrame, x: str, y: str, top: int) -> pd.Series:
    """x 를 인덱스로, y 를 값으로 하는 상위 top 시리즈."""
    return frame.head(max(0, top)).set_index(x)[y]


def line_data(frame: pd.DataFrame, x: str) -> pd.DataFrame:
    """x 를 인덱스로, 수치 열만 선으로. 문자열/혼합 열은 뺀다(차트가 못 그린다)."""
    return frame.set_index(x).select_dtypes(include="number")


def heatmap_pivot(frame: pd.DataFrame, from_col: str, to_col: str,
                  value: str) -> pd.DataFrame:
    """(from, to) 격자. 값은 value 열."""
    return frame.pivot_table(index=from_col, columns=to_col, values=value,
                             aggfunc="sum", fill_value=0)

from __future__ import annotations

import duckdb
import pandas as pd


def join_dim(
    events: pd.DataFrame,
    dim: pd.DataFrame,
    key: str = "app_user_id",
    how: str = "left",
) -> pd.DataFrame:
    """이벤트에 차원(유저 속성) 테이블을 로컬 DuckDB로 조인."""
    join_kw = {"left": "LEFT", "inner": "INNER"}[how]
    con = duckdb.connect()
    try:
        con.register("events", events)
        con.register("dim", dim)
        result = con.execute(
            f"SELECT events.*, dim.* EXCLUDE ({key}) "
            f"FROM events {join_kw} JOIN dim USING ({key})"
        ).df()
    finally:
        con.close()
    # DuckDB's .df() yields pandas' "str" extension dtype for text columns,
    # whose missing-value sentinel round-trips through .where(...) as float
    # NaN rather than Python None. Cast to plain object dtype first so
    # unmatched dim values surface as None (matches how the tests assert
    # missing values), not NaN.
    text_cols = result.select_dtypes(include=["object", "str"]).columns
    if len(text_cols):
        result[text_cols] = result[text_cols].astype(object)
        result[text_cols] = result[text_cols].where(result[text_cols].notna(), None)
    return result

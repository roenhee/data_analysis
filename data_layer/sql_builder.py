from __future__ import annotations

from data_layer.sources import SourceDef


def _full_source_table(source: SourceDef) -> str:
    return f"{source.catalog}.{source.schema}.{source.table}"


def _select_columns(source: SourceDef) -> str:
    return ",\n        ".join(
        f"{expr} AS {flat}" for flat, expr in source.column_map.items()
    )


def _where_clause(source: SourceDef, extra: list[str]) -> str:
    conds = ["1=1", *source.filters, *extra]
    return "\n      AND ".join(conds)


def _deterministic_uniform(seed: int) -> str:
    key = f"app_user_id || '|' || isuid || '|' || CAST({int(seed)} AS VARCHAR)"
    return f"(from_base(substr(to_hex(md5(to_utf8({key}))), 1, 8), 16) / 4294967295.0)"


def build_prepare_sql(
    source: SourceDef,
    temp_table: str,
    window: tuple[str, str],
    seed: int,
    target_rows: int,
) -> str:
    start, end = window
    cols = _select_columns(source)
    where = _where_clause(
        source,
        [
            f"try_cast(common.access_time AS timestamp) BETWEEN TIMESTAMP '{start} 00:00:00' AND TIMESTAMP '{end} 23:59:59'"
        ],
    )
    uni = _deterministic_uniform(seed)
    return f"""CREATE OR REPLACE TABLE {temp_table} AS
WITH base AS (
    SELECT
        {cols},
        try_cast(common.access_time AS timestamp) AS _access_ts
    FROM {_full_source_table(source)}
    WHERE {where}
),
base2 AS (
    SELECT * FROM base WHERE _access_ts IS NOT NULL
),
session_meta AS (
    SELECT app_user_id, isuid,
        date_trunc('hour', min(_access_ts)) AS session_start_hour,
        CAST(date(min(_access_ts)) AS varchar) AS start_day,
        count(*) AS session_rows
    FROM base2 GROUP BY 1,2
),
hour_stats AS (
    SELECT session_start_hour, sum(session_rows) AS hour_total_rows
    FROM session_meta GROUP BY 1
),
picked AS (
    SELECT m.app_user_id, m.isuid, m.start_day
    FROM session_meta m JOIN hour_stats h ON m.session_start_hour = h.session_start_hour
    WHERE {uni} < least(1.0, {int(target_rows)}.0 / (h.hour_total_rows * 1.0))
)
SELECT b.*, p.start_day
FROM base2 b JOIN picked p ON b.app_user_id = p.app_user_id AND b.isuid = p.isuid
"""


def build_partition_sql(temp_table: str, start_day: str) -> str:
    return f"SELECT * FROM {temp_table} WHERE start_day = DATE '{start_day}'"


def build_action_counts_sql(source: SourceDef, window: tuple[str, str]) -> str:
    start, end = window
    name_expr = source.column_map.get("action_name", "action.name")
    where = _where_clause(
        source,
        [
            f"try_cast(common.access_time AS timestamp) BETWEEN TIMESTAMP '{start} 00:00:00' AND TIMESTAMP '{end} 23:59:59'"
        ],
    )
    return f"""SELECT {name_expr} AS action_name, COUNT(*) AS cnt
FROM {_full_source_table(source)}
WHERE {where}
GROUP BY {name_expr}
ORDER BY cnt DESC
"""

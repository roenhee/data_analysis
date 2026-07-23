from __future__ import annotations

from data_layer.sources import SourceDef

# breakdown/filter로 허용되는 화이트리스트 컬럼 (저카디널리티 → 카디널리티 폭발 차단)
BREAKDOWN_WHITELIST = ("app_version", "os", "service_code")


def _col(source: SourceDef, flat: str, default: str) -> str:
    return source.column_map.get(flat, default)


def _table(source: SourceDef) -> str:
    return f"{source.catalog}.{source.schema}.{source.table}"


def _escape(value) -> str:
    return str(value).replace("'", "''")


def _where(source: SourceDef, window: tuple[str, str], filters: dict) -> str:
    start, end = window
    ts = _col(source, "access_time", "try_cast(common.access_time AS timestamp)")
    conds = ["1=1", *source.filters]
    conds.append(f"{ts} BETWEEN TIMESTAMP '{start} 00:00:00' AND TIMESTAMP '{end} 23:59:59'")
    for key, val in filters.items():
        conds.append(f"{_col(source, key, key)} = '{_escape(val)}'")
    return "\n      AND ".join(conds)


def _period_expr(source: SourceDef, grain: str) -> str:
    ts = _col(source, "access_time", "try_cast(common.access_time AS timestamp)")
    return f"date_trunc('{grain}', {ts})"


def _breakdown_selects(source: SourceDef, breakdown: list) -> list:
    return [f"{_col(source, b, b)} AS {b}" for b in breakdown]


def _assemble(select_lines: list, source: SourceDef, window: tuple[str, str], filters: dict, n_dims: int) -> str:
    group_by = ", ".join(str(n) for n in range(1, 2 + n_dims))   # period(+breakdown)
    return (
        "SELECT\n    " + ",\n    ".join(select_lines)
        + f"\nFROM {_table(source)}"
        + f"\nWHERE {_where(source, window, filters)}"
        + f"\nGROUP BY {group_by}\nORDER BY {group_by}\n"
    )


def build_uv_pv_sql(source: SourceDef, window: tuple[str, str], grain: str, breakdown: list, filters: dict) -> str:
    """기간(period)별 UV/PV 전수 집계 SQL. breakdown은 period 위에 얹는 추가 GROUP BY 축."""
    au = _col(source, "app_user_id", "user.app_user_id")
    at = _col(source, "action_type", "action.type")
    lines = [
        f"{_period_expr(source, grain)} AS period",
        *_breakdown_selects(source, breakdown),
        f"COUNT(DISTINCT {au}) AS uv",
        f"COUNT(*) FILTER (WHERE {at} = 'Pageview') AS pv",
    ]
    return _assemble(lines, source, window, filters, len(breakdown))


def build_session_engagement_sql(source: SourceDef, window: tuple[str, str], grain: str, breakdown: list, filters: dict) -> str:
    """세션 engagement 전수 집계 SQL. 세션 = (app_user_id, isuid).

    체류시간 = 세션 span = date_diff(초, 첫 이벤트, 마지막 이벤트). 각 세션은 첫 이벤트
    기준 period·breakdown 값에 귀속한다(min_by). breakdown은 period 위 추가 축.
    """
    au = _col(source, "app_user_id", "user.app_user_id")
    isuid = _col(source, "isuid", "user.isuid")
    ts = _col(source, "access_time", "try_cast(common.access_time AS timestamp)")
    sess_lines = [
        f"{au} AS app_user_id",
        f"{isuid} AS isuid",
        f"min({ts}) AS t0",
        f"max({ts}) AS t1",
        f"date_trunc('{grain}', min({ts})) AS period",
        *[f"min_by({_col(source, b, b)}, {ts}) AS {b}" for b in breakdown],
    ]
    cte = (
        "WITH sess AS (\n    SELECT\n        "
        + ",\n        ".join(sess_lines)
        + f"\n    FROM {_table(source)}"
        + f"\n    WHERE {_where(source, window, filters)}"
        + f"\n    GROUP BY {au}, {isuid}\n)"
    )
    out_lines = [
        "period",
        *breakdown,
        "count(*) AS sessions",
        "count(DISTINCT app_user_id) AS uv",
        "sum(date_diff('second', t0, t1)) AS total_duration",
    ]
    group_by = ", ".join(str(n) for n in range(1, 2 + len(breakdown)))
    return (
        cte
        + "\nSELECT\n    "
        + ",\n    ".join(out_lines)
        + f"\nFROM sess\nGROUP BY {group_by}\nORDER BY {group_by}\n"
    )

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

"""state 사전 생성용 집계 SQL. 전이를 계산하지 않으므로 가볍다."""
from __future__ import annotations

BASE_FILTERS = (
    "NULLIF(TRIM(user.uuid), '') IS NOT NULL",
    "NULLIF(TRIM(user.suid), '') IS NOT NULL",
    "try_cast(common.access_time AS timestamp) IS NOT NULL",
    "coalesce(tag.is_invalid, '0') <> '1'",
)


def _lit(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _in_list(values) -> str:
    return ", ".join(_lit(v) for v in values)


def _where(window: tuple[str, str], services: list[str], extra: list[str]) -> str:
    start, end = window
    # 뒤집힌 구간은 BETWEEN 을 불만족으로 만들어 조용히 0행을 낸다. 에러도 안 나고
    # 사전이 빈 채로 만들어지므로 여기서 막는다. ISO 날짜라 문자열 비교로 충분하다.
    if end < start:
        raise ValueError(f"window end {end!r} precedes start {start!r}")
    conds = [
        f"date_id BETWEEN {_lit(start)} AND {_lit(end)}",
        f"c_service_code IN ({_in_list(services)})",
        *BASE_FILTERS,
        *extra,
    ]
    return "\n  AND ".join(conds)


def _count_sql(table, window, services, value_expr, extra) -> str:
    # 채택 가중 = **고유 세션 수**(`approx_distinct(세션키)`), `count(*)`(이벤트 행) 아님.
    # 행수 가중은 허브 화면 재방문·미플래그 반복을 부풀려 소규모 서비스를 굶긴다(측정:
    # docs/superpowers/measurements/2026-08-11-state-dict-weighting.md). 세션키=(uuid,suid);
    # BASE_FILTERS 가 둘의 non-null 을 보장하므로 concat 이 안전하다. is_invalid 봇은 이미 제외.
    return (
        f"SELECT {value_expr} AS value,\n"
        "  approx_distinct(user.uuid || '|' || user.suid) AS cnt\n"
        f"FROM {table}\n"
        f"WHERE {_where(window, services, extra)}\n"
        "GROUP BY 1\n"
        "ORDER BY 2 DESC\n"
    )


def build_screen_count_sql(table: str, window, services) -> str:
    """화면(`service_code/Pageview name`)별 건수."""
    value = (
        "c_service_code || '/' || "
        "coalesce(nullif(trim(action.name), ''), '(none)')"
    )
    return _count_sql(table, window, services, value, ["action.type = 'Pageview'"])


def build_layer1_count_sql(table: str, window, services) -> str:
    value = "nullif(trim(click.layer1), '')"
    return _count_sql(
        table, window, services, value,
        ["nullif(trim(click.layer1), '') IS NOT NULL"],
    )


def build_layer2_count_sql(table: str, window, services) -> str:
    value = (
        "nullif(trim(click.layer1), '') || '>' || "
        "coalesce(nullif(trim(click.layer2), ''), '(none)')"
    )
    return _count_sql(
        table, window, services, value,
        ["nullif(trim(click.layer1), '') IS NOT NULL"],
    )


def build_version_count_sql(table: str, window, services) -> str:
    value = "nullif(trim(env.app_version), '')"
    return _count_sql(
        table, window, services, value,
        ["nullif(trim(env.app_version), '') IS NOT NULL"],
    )

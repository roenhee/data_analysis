"""큐브 집계 SQL. 서버에 테이블을 만들지 않고 CTE 단일 SELECT로 수행한다.

세션은 첫 이벤트 날짜에 귀속한다. 축 값도 첫 이벤트 기준(`min_by`)이므로 세션 하나가
날짜·버전·시간대 축에서 쪼개지지 않는다.

날짜 `D` 빌드는 **`date_id IN (D-1, D, D+1)` 세 파티션**을 읽고 첫 이벤트가 `D` 인 세션만
채택한다. `D+1` 은 자정을 넘긴 세션의 꼬리를 확보하기 위한 것이고, **`D-1` 은 중복 집계를
막기 위한 것이다** — `D-1` 을 읽지 않으면 `D-1` 에 시작해 `D` 로 넘어온 세션의 꼬리를
`D` 빌드가 자기 창 밖의 첫 이벤트를 못 봐서 "`D` 에 시작한 세션"으로 판정하고, `D-1`
빌드가 이미 온전히 센 것을 한 번 더 센다.
"""
from __future__ import annotations

from analytics.cube.axes import CORE_AXIS_NAMES, core_axis_selects
from analytics.cube.state_sql import BASE_FILTERS, _in_list, _lit


def _event_cte(
    events_table: str,
    demography_table: str,
    window_dates: list[str],
    services: list[str],
    versions: list[str],
) -> str:
    """`window_dates` 파티션의 이벤트에 성연령을 붙이고 축을 계산한 CTE.

    `window_dates` 는 보통 `[D-1, D, D+1]` 이다. `D+1` 은 자정을 넘긴 세션의 꼬리를
    확보하고, **`D-1` 은 중복 집계를 막는다** — 없으면 `D-1` 에 시작해 `D` 로 넘어온 세션의
    꼬리를 `D` 빌드가 "`D` 에 시작한 세션"으로 오판해 두 번 센다.
    """
    axis_selects = ",\n    ".join(core_axis_selects(versions))
    conds = "\n      AND ".join(
        [
            f"date_id IN ({_in_list(window_dates)})",
            f"c_service_code IN ({_in_list(services)})",
            *BASE_FILTERS,
        ]
    )
    return (
        "WITH ev AS (\n"
        "  SELECT\n"
        f"    {axis_selects},\n"
        "    user.uuid AS uuid,\n"
        "    user.suid AS suid,\n"
        "    try_cast(common.access_time AS timestamp) AS ts,\n"
        "    action.type AS action_type,\n"
        "    action.kind AS action_kind,\n"
        "    action.name AS action_name,\n"
        "    c_service_code AS service_code,\n"
        "    common.page AS page,\n"
        "    click.layer1 AS layer1,\n"
        "    click.layer2 AS layer2,\n"
        "    try(cast(usage.duration AS double)) AS usage_duration\n"
        f"  FROM {events_table}\n"
        f"  LEFT JOIN {demography_table} d ON d.uuid = user.uuid\n"
        f"  WHERE {conds}\n"
        ")"
    )


def _grouping_sets(axes: tuple[str, ...]) -> str:
    """전체 조합 + 축을 하나씩 ALL로 접은 조합 + 전체 롤업.

    uv 는 가산이 아니므로 클라이언트가 합산할 수 없다. 자주 쓰는 롤업을 미리 만든다.
    """
    full = "(" + ", ".join(axes) + ")"
    folded = [
        "(" + ", ".join(a for a in axes if a != drop) + ")"
        for drop in axes
        if drop != "period"
    ]
    period_only = "(period)"
    sets = [full, *folded, period_only, "()"]
    return "GROUPING SETS (\n    " + ",\n    ".join(sets) + "\n  )"


def build_session_cube_sql(
    events_table: str,
    demography_table: str,
    date: str,
    window_dates: list[str],
    services: list[str],
    versions: list[str],
) -> str:
    """`date` 에 시작한 세션만 집계한다. `window_dates` 는 읽을 파티션 목록이다."""
    axes = CORE_AXIS_NAMES
    axis_list = ", ".join(axes)
    first_axes = ",\n    ".join(f"min_by({a}, ts) AS {a}" for a in axes)
    return (
        _event_cte(events_table, demography_table, window_dates, services, versions)
        + ",\nsess AS (\n"
        "  SELECT\n"
        "    uuid,\n"
        "    suid,\n"
        f"    {first_axes},\n"
        "    count(*) AS events,\n"
        "    count_if(action_type = 'Pageview') AS pv,\n"
        "    date_diff('second', min(ts), max(ts)) AS duration_sec\n"
        "  FROM ev\n"
        "  GROUP BY uuid, suid\n"
        f"  HAVING date(min(ts)) = date({_lit(date)})\n"
        ")\n"
        "SELECT\n"
        f"  {axis_list},\n"
        "  count(*) AS sessions,\n"
        "  count(DISTINCT uuid) AS uv,\n"
        "  sum(pv) AS pv,\n"
        "  sum(events) AS events,\n"
        "  sum(duration_sec) AS duration_sum\n"
        "FROM sess\n"
        "GROUP BY " + _grouping_sets(axes) + "\n"
    )

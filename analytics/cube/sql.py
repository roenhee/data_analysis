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


def _first_event_axes(indent: str = "    ") -> str:
    """세션의 축 값을 첫 이벤트로 고정하는 SELECT 절. 세션이 축에서 쪼개지지 않게 한다."""
    return (",\n" + indent).join(
        f"min_by({a}, ts) AS {a}" for a in CORE_AXIS_NAMES
    )


def _first_event_attribution(date: str) -> str:
    """세션을 첫 이벤트 날짜에 귀속시키는 FROM/GROUP BY/HAVING.

    **모든 큐브가 이 한 절을 공유한다.** 복사본을 두면 반드시 갈라지고, 갈라지면 같은
    세션이 큐브마다 다른 날짜·daypart 버킷에 앉아 큐브 간 조인이 조용히 깨진다.

    원천은 반드시 `ev`(전체 이벤트)다. Pageview 로 좁힌 뒤 귀속하면 첫 이벤트가
    비-Pageview 인 세션의 귀속 날짜·축이 어긋난다 — `top` 이벤트의 90%가 비-Pageview라
    그런 세션이 다수다.
    """
    return (
        "  FROM ev\n"
        "  GROUP BY uuid, suid\n"
        f"  HAVING date(min(ts)) = date({_lit(date)})\n"
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
    return (
        _event_cte(events_table, demography_table, window_dates, services, versions)
        + ",\nsess AS (\n"
        "  SELECT\n"
        "    uuid,\n"
        "    suid,\n"
        f"    {_first_event_axes()},\n"
        "    count(*) AS events,\n"
        "    count_if(action_type = 'Pageview') AS pv,\n"
        "    date_diff('second', min(ts), max(ts)) AS duration_sec\n"
        + _first_event_attribution(date)
        + ")\n"
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


def build_transition_cube_sql(
    events_table: str,
    demography_table: str,
    date: str,
    window_dates: list[str],
    services: list[str],
    versions: list[str],
    screens: list[str],
) -> str:
    """화면 전이 큐브. START/EXIT를 명시 상태로 추가한다.

    세션 모집단과 축 좌표는 `build_session_cube_sql` 과 **같은 첫-이벤트 귀속**을 쓴다
    (`kept` 가 `screens` 가 아니라 `ev` 에서 나온다). Pageview 없는 세션은 `screens` 와의
    조인에서 자연히 빠지므로 따로 거를 필요가 없다.
    """
    axes = CORE_AXIS_NAMES
    axis_cols = "k." + ", k.".join(axes)
    screen_raw = (
        "service_code || '/' || coalesce(nullif(trim(action_name), ''), '(none)')"
    )
    if screens:
        screen_expr = (
            f"CASE WHEN {screen_raw} IN ({_in_list(screens)})\n"
            f"         THEN {screen_raw}\n"
            "         ELSE service_code || '/other' END"
        )
    else:
        screen_expr = "service_code || '/other'"
    return (
        _event_cte(events_table, demography_table, window_dates, services, versions)
        + ",\nkept AS (\n"
        "  SELECT\n"
        "    uuid,\n"
        "    suid,\n"
        f"    {_first_event_axes()}\n"
        + _first_event_attribution(date)
        + "),\n"
        "screens AS (\n"
        "  SELECT uuid, suid, ts, usage_duration,\n"
        f"    {screen_expr} AS state\n"
        "  FROM ev\n"
        "  WHERE action_type = 'Pageview'\n"
        "),\n"
        "seq AS (\n"
        "  SELECT s.uuid, s.suid, s.ts, s.state, s.usage_duration,\n"
        # `screens` 와 `kept` 가 둘 다 uuid/suid 를 내보내므로 반드시 한정해야 한다.
        # 한정하지 않으면 Trino/DuckDB 모두 "Ambiguous reference" 로 죽는다.
        "    row_number() OVER (PARTITION BY s.uuid, s.suid ORDER BY s.ts) AS rn,\n"
        "    lead(s.state) OVER (PARTITION BY s.uuid, s.suid ORDER BY s.ts)\n"
        "      AS next_state\n"
        "  FROM screens s\n"
        "  JOIN kept k ON k.uuid = s.uuid AND k.suid = s.suid\n"
        "),\n"
        "edges AS (\n"
        "  SELECT uuid, suid, state AS from_state,\n"
        "         coalesce(next_state, 'EXIT') AS to_state, usage_duration\n"
        "  FROM seq\n"
        "  UNION ALL\n"
        "  SELECT uuid, suid, 'START' AS from_state, state AS to_state, 0.0\n"
        "  FROM seq WHERE rn = 1\n"
        ")\n"
        "SELECT\n"
        f"  {axis_cols},\n"
        "  e.from_state,\n"
        "  e.to_state,\n"
        "  count(*) AS cnt,\n"
        "  coalesce(sum(e.usage_duration), 0) AS dur_sum\n"
        "FROM edges e\n"
        "JOIN kept k ON k.uuid = e.uuid AND k.suid = e.suid\n"
        f"GROUP BY {axis_cols}, e.from_state, e.to_state\n"
    )

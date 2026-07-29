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
        # 원천은 **밀리초**다. 증거: `top` 하루치 최대값이 10,799,978 = 정확히 3시간으로
        # 서버측 상한값이고(초로 보면 125일), 중앙값 5,285 = 5.3초다. 이름에 단위를 박아
        # 세션 큐브의 `duration_sum`(date_diff 초)과 섞이지 않게 한다.
        "    try(cast(usage.duration AS double)) AS usage_duration_ms\n"
        f"  FROM {events_table}\n"
        f"  LEFT JOIN {demography_table} d ON d.uuid = user.uuid\n"
        f"  WHERE {conds}\n"
        ")"
    )


def _first_event_axes(date: str, indent: str = "    ") -> str:
    """세션의 축 값을 첫 이벤트로 고정하는 SELECT 절. 세션이 축에서 쪼개지지 않게 한다.

    **`period` 만 예외로 빌드 날짜 상수다.** 나머지 축처럼 `min_by(period, ts)` 로 두면
    `period` 가 첫 이벤트의 `date_id`(그 이벤트가 **쓰인 파티션**)가 되는데, 귀속은
    `date(min(ts))`(첫 이벤트의 **access_time 날짜**)로 한다. 둘은 항상 같지 않다 —
    실측 45.7만 세션 중 42만(0.0919%)이 어긋났고, 자정 직전 이벤트가 다음 날 파티션에
    쓰이는 탓에 D+1 쪽으로 크게 치우쳤다(파일당 D-1 은 50~100건, D+1 은 1.8만~4.9만건).

    그 결과 14일치를 이어붙여 `period` 로 묶으면 **한 period 에 롤업 행이 두 개** 나온다
    (D 파일과 D+1 파일이 둘 다 그 period 행을 갖는다). 눈치 못 채고 합산하면 조용히 2배가
    된다. 귀속이 `date(min(ts)) = date` 를 보장하므로 `period` 는 상수여야 맞다.
    """
    parts = []
    for axis in CORE_AXIS_NAMES:
        if axis == "period":
            parts.append(f"{_lit(date)} AS period")
        else:
            parts.append(f"min_by({axis}, ts) AS {axis}")
    return (",\n" + indent).join(parts)


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
        f"    {_first_event_axes(date)},\n"
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

    **체류시간은 Pageview 행에 없다.** 실측(2026-07-27, `top`): Pageview 1억 7,214만 행의
    `usage.duration` 비NULL이 **0건**이고, 체류는 전부 `Usage`+`UsagePage` 행(1억 3,923만 중
    99.9%)에 실린다. 그래서 두 신호를 한 스트림으로 합친 뒤 `visit_idx`(그 행까지의 Pageview
    수)로 **각 Usage 행을 직전 화면 방문에 묶는다**. 방문 하나가 여러 Usage 행을 낼 수 있어
    (`media` 는 Pageview 대비 107%) 방문 단위로 먼저 합친다.

    `cnt` 는 이 변경의 영향을 받지 않는다 — 상태를 만드는 것은 여전히 Pageview 행뿐이다.

    `dur_sum` 의 단위는 **초**다. 원천 `usage.duration` 은 밀리초이므로 1000으로 나눈다
    (증거는 `_event_cte` 의 주석). 세션 큐브의 `duration_sum` 과 같은 단위다.

    **`dur_n` 을 반드시 같이 읽어라.** 체류 커버리지는 축마다 다르다(실측: `search` 0%,
    `top` 웹 65.6%, `top` android 84.8%, `media` 107%). `dur_sum / cnt` 는 커버리지만큼
    조용히 축소된 값이므로 **틀렸다**. 옳은 값은 `dur_sum / dur_n` 이고, 이는 "체류가
    측정된 방문"에 대한 조건부 평균이다. `dur_n / cnt` 가 그 셀의 커버리지다.

    **얇은 셀의 체류는 믿지 마라.** 실측 엣지 셀의 cnt 중앙값은 9이고 18.9%는 1이다.
    엣지 단위 평균 체류는 두꺼운 셀에서만 의미가 있다. `dur_sum`·`dur_n` 은 둘 다 가산이니
    필요하면 `to_state` 로 합쳐 화면 단위(중앙값 5.6배)로 올려서 본다.
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
        f"    {_first_event_axes(date)}\n"
        + _first_event_attribution(date)
        + "),\n"
        # 화면 신호(Pageview)와 체류 신호(Usage/UsagePage)를 한 스트림으로 합친다.
        "stream AS (\n"
        "  SELECT uuid, suid, ts,\n"
        f"    CASE WHEN action_type = 'Pageview' THEN {screen_expr} END AS state,\n"
        # ms -> 초. 세션 큐브의 duration_sum 과 같은 단위여야 두 큐브를 같이 읽는다.
        "    CASE WHEN action_type = 'Usage'\n"
        "         THEN usage_duration_ms / 1000.0 END AS dwell,\n"
        "    CASE WHEN action_type = 'Pageview' THEN 1 ELSE 0 END AS is_screen\n"
        "  FROM ev\n"
        "  WHERE action_type = 'Pageview'\n"
        "     OR (action_type = 'Usage' AND action_kind = 'UsagePage')\n"
        "),\n"
        # 각 행을 직전 화면 방문에 묶는다. 같은 ts 면 Pageview 가 먼저 와야 그 방문에
        # 붙는다 — 안 그러면 체류가 앞 방문으로 새어 간다.
        "marked AS (\n"
        "  SELECT uuid, suid, ts, state, dwell, is_screen,\n"
        "    sum(is_screen) OVER (PARTITION BY uuid, suid ORDER BY ts, is_screen DESC\n"
        "      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS visit_idx\n"
        "  FROM stream\n"
        "),\n"
        # 방문 하나가 여러 UsagePage 행을 낼 수 있으므로 방문 단위로 먼저 합친다.
        # visit_idx = 0 은 첫 화면보다 앞선 Usage 행이라 귀속할 방문이 없다.
        "visit_dwell AS (\n"
        "  SELECT uuid, suid, visit_idx, sum(dwell) AS dwell_sum\n"
        "  FROM marked\n"
        "  WHERE is_screen = 0 AND visit_idx > 0 AND dwell IS NOT NULL\n"
        "  GROUP BY uuid, suid, visit_idx\n"
        "),\n"
        "screens AS (\n"
        "  SELECT m.uuid, m.suid, m.ts, m.state, v.dwell_sum\n"
        "  FROM marked m\n"
        "  LEFT JOIN visit_dwell v\n"
        "    ON v.uuid = m.uuid AND v.suid = m.suid AND v.visit_idx = m.visit_idx\n"
        "  WHERE m.is_screen = 1\n"
        "),\n"
        "seq AS (\n"
        "  SELECT s.uuid, s.suid, s.ts, s.state, s.dwell_sum,\n"
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
        "         coalesce(next_state, 'EXIT') AS to_state, dwell_sum\n"
        "  FROM seq\n"
        "  UNION ALL\n"
        # START 는 화면이 아니라 체류가 없다. 첫 화면의 체류를 여기 붙이면 같은 체류가
        # START 엣지와 그 화면의 출발 엣지에 두 번 들어간다.
        "  SELECT uuid, suid, 'START' AS from_state, state AS to_state,\n"
        "         CAST(NULL AS double)\n"
        "  FROM seq WHERE rn = 1\n"
        ")\n"
        "SELECT\n"
        f"  {axis_cols},\n"
        "  e.from_state,\n"
        "  e.to_state,\n"
        "  count(*) AS cnt,\n"
        "  coalesce(sum(e.dwell_sum), 0) AS dur_sum,\n"
        # 체류가 측정된 방문 수. `dur_sum / dur_n` 이 조건부 평균이고,
        # `dur_n / cnt` 가 이 셀의 체류 커버리지다.
        "  count(e.dwell_sum) AS dur_n\n"
        "FROM edges e\n"
        "JOIN kept k ON k.uuid = e.uuid AND k.suid = e.suid\n"
        f"GROUP BY {axis_cols}, e.from_state, e.to_state\n"
    )


QUALITY_CHECKS = (
    "null_action_name",
    "pageview_null_kind",
    "screen_other_ratio",
    "session_no_screen",
    "page_name_ambiguous",
    "session_span_exceeds_timeout",
    "screen_without_dwell",
    "exit_without_appexit",
)


def build_quality_cube_sql(
    events_table: str,
    date: str,
    window_dates: list[str],
    services: list[str],
) -> str:
    """정합성 검사 큐브.

    품질 자체를 재는 쿼리이므로 `tag.is_invalid` 필터를 적용하지 않는다. 필터를 걸면
    측정 대상이 사라진다.

    **창 규약**: `window_dates`(보통 `[D-1, D, D+1]`)를 읽되 용도가 갈린다.

    - *행 단위* 검사는 `day` CTE(대상 파티션 `D`)만 본다. 3일치를 세면 분모가 부푼다.
    - *세션 단위* 검사는 창 전체를 보고 다른 큐브와 **같은 첫-이벤트 귀속**을 쓴다.
      단일 파티션으로 재면 자정을 넘긴 세션의 span 이 절단돼
      `session_span_exceeds_timeout` 이 감시 대상인 바로 그 세션을 못 본다 —
      D-1 22:00 ~ D 04:01(6시간 1분) 세션은 양쪽 빌드 모두에서 6시간 미만으로 보인다.

    `total` 은 검사마다 분모가 다르다: 행 검사는 이벤트 수, 세션 검사는 세션 수,
    `page_name_ambiguous` 는 화면 이름 종수, `screen_other_ratio` 는 Pageview 행 수다.

    `screen_other_ratio` 는 `/other` 로 접히는 비율의 **하한**이다. 사전에 없는 이름도
    `/other` 로 접히지만 이 쿼리는 state 사전을 모르므로 NULL 이름만 센다.

    `screen_without_dwell` 은 체류가 측정되지 않은 화면 방문 비율이다(분모 = 방문 수).
    체류 커버리지가 축마다 크게 다르기 때문에(실측: `search` 0%, `top` 웹 65.6%,
    `top` android 84.8%) 두 세그먼트의 체류를 비교해도 되는지는 이 검사로 판단한다.
    **유효 조건은 "커버리지가 높다"가 아니라 "비교 대상 둘의 커버리지가 같다"** 이다 —
    65.6%짜리 웹끼리의 버전 비교는 유효하고, 88% android 와 66% 웹의 비교는 무효다.
    셀 단위의 정확한 커버리지는 transition 큐브의 `dur_n / cnt` 를 쓴다. 이 검사는
    그보다 거친 일별·서비스별 추세 감시용이다(단일 파티션이라 자정 횡단 방문은 절단된다).
    """
    where = (
        f"date_id IN ({_in_list(window_dates)})\n"
        f"      AND c_service_code IN ({_in_list(services)})\n"
        "      AND NULLIF(TRIM(user.uuid), '') IS NOT NULL\n"
        "      AND NULLIF(TRIM(user.suid), '') IS NOT NULL"
    )
    return (
        "WITH ev AS (\n"
        "  SELECT\n"
        "    date_id AS period,\n"
        "    c_service_code AS service_code,\n"
        "    coalesce(env.app_version, 'unknown') AS app_version,\n"
        "    user.uuid AS uuid,\n"
        "    user.suid AS suid,\n"
        "    action.type AS action_type,\n"
        "    action.kind AS action_kind,\n"
        "    nullif(trim(action.name), '') AS action_name,\n"
        "    nullif(trim(common.page), '') AS page,\n"
        "    try_cast(common.access_time AS timestamp) AS ts\n"
        f"  FROM {events_table}\n"
        f"  WHERE {where}\n"
        "),\n"
        # 행 단위 검사는 대상 파티션만 본다. 창은 세션 검사 전용이다.
        "day AS (\n"
        f"  SELECT * FROM ev WHERE period = {_lit(date)}\n"
        "),\n"
        "row_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(action_name IS NULL) AS null_action_name,\n"
        "    count_if(action_type = 'Pageview' AND action_kind IS NULL)"
        " AS pageview_null_kind\n"
        "  FROM day GROUP BY 1, 2\n"
        "),\n"
        # 세션 검사는 다른 큐브와 같은 귀속을 쓴다 — 같은 세션 모집단을 재야 한다.
        "sess AS (\n"
        "  SELECT uuid, suid,\n"
        "    min_by(service_code, ts) AS service_code,\n"
        "    min_by(app_version, ts) AS app_version,\n"
        "    count_if(action_type = 'Pageview') AS pv,\n"
        "    date_diff('second', min(ts), max(ts)) AS span_sec\n"
        + _first_event_attribution(date)
        + "),\n"
        "sess_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(pv = 0) AS session_no_screen,\n"
        # 세션 타임아웃 계약(앱 300초·웹 1800초) 위반. 이 비율이 커지면 자정 경계
        # 중복집계 위험도 커진다 — 스펙의 잔여 한계 항목 참조.
        "    count_if(span_sec > 21600) AS session_span_exceeds_timeout\n"
        "  FROM sess GROUP BY 1, 2\n"
        "),\n"
        "name_pages AS (\n"
        "  SELECT service_code, app_version, action_name,\n"
        "    count(DISTINCT page) AS pages\n"
        "  FROM day WHERE action_type = 'Pageview' AND action_name IS NOT NULL\n"
        "  GROUP BY 1, 2, 3\n"
        "),\n"
        "page_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(pages > 1) AS page_name_ambiguous\n"
        "  FROM name_pages GROUP BY 1, 2\n"
        "),\n"
        "screen_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(action_name IS NULL) AS screen_other_ratio\n"
        "  FROM day WHERE action_type = 'Pageview' GROUP BY 1, 2\n"
        "),\n"
        # 체류 커버리지. transition 큐브의 방문 귀속과 같은 규칙으로 센다.
        "dwell_stream AS (\n"
        "  SELECT service_code, app_version, uuid, suid, ts,\n"
        "    CASE WHEN action_type = 'Pageview' THEN 1 ELSE 0 END AS is_screen,\n"
        "    CASE WHEN action_type = 'Usage' THEN 1 ELSE 0 END AS is_dwell\n"
        "  FROM day\n"
        "  WHERE action_type = 'Pageview'\n"
        "     OR (action_type = 'Usage' AND action_kind = 'UsagePage')\n"
        "),\n"
        "dwell_marked AS (\n"
        "  SELECT service_code, app_version, uuid, suid, is_dwell,\n"
        "    sum(is_screen) OVER (PARTITION BY uuid, suid ORDER BY ts, is_screen DESC\n"
        "      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS visit_idx\n"
        "  FROM dwell_stream\n"
        "),\n"
        "visits AS (\n"
        "  SELECT service_code, app_version, uuid, suid, visit_idx,\n"
        "    max(is_dwell) AS has_dwell\n"
        "  FROM dwell_marked WHERE visit_idx > 0\n"
        "  GROUP BY 1, 2, 3, 4, 5\n"
        "),\n"
        "dwell_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(has_dwell = 0) AS screen_without_dwell\n"
        "  FROM visits GROUP BY 1, 2\n"
        "),\n"
        # 이탈 정의의 삼각측량. 앱 세션만 분모에 넣는다 — 웹에는 종료 이벤트가 없어서
        # 섞으면 검사가 "웹 비중"을 재게 된다.
        "exit_sess AS (\n"
        "  SELECT uuid, suid,\n"
        "    min_by(service_code, ts) AS service_code,\n"
        "    min_by(app_version, ts) AS app_version,\n"
        "    max(CASE WHEN action_type = 'Pageview' THEN ts END) AS last_pv,\n"
        "    max(CASE WHEN action_type = 'App' AND action_kind = 'AppExit'\n"
        "             THEN ts END) AS last_exit,\n"
        "    count_if(action_type = 'App') AS app_events\n"
        + _first_event_attribution(date)
        + "),\n"
        "exit_checks AS (\n"
        "  SELECT service_code, app_version,\n"
        "    count(*) AS total,\n"
        "    count_if(last_exit IS NULL OR last_exit < last_pv)"
        " AS exit_without_appexit\n"
        "  FROM exit_sess\n"
        "  WHERE last_pv IS NOT NULL AND app_events > 0\n"
        "  GROUP BY 1, 2\n"
        ")\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'null_action_name' AS check_name,\n"
        "       null_action_name AS violated, total AS total FROM row_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'pageview_null_kind', pageview_null_kind, total FROM row_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'screen_other_ratio', screen_other_ratio, total FROM screen_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'session_no_screen', session_no_screen, total FROM sess_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'page_name_ambiguous', page_name_ambiguous, total FROM page_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'session_span_exceeds_timeout', session_span_exceeds_timeout,"
        " total FROM sess_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'screen_without_dwell', screen_without_dwell, total"
        " FROM dwell_checks\n"
        "UNION ALL\n"
        f"SELECT service_code, app_version, {_lit(date)} AS period,\n"
        "       'exit_without_appexit', exit_without_appexit, total"
        " FROM exit_checks\n"
    )

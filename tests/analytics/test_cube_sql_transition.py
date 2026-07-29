from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import build_transition_cube_sql

ARGS = dict(
    events_table="bigdata_omega_common_iceberg.axz_tiara.all_tiara_n",
    demography_table="hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2",
    date="2026-07-27",
    window_dates=["2026-07-26", "2026-07-27", "2026-07-28"],
    services=["top"],
    versions=["9.5.1"],
    screens=["top/홈탭_진입", "top/콘텐츠탭_진입"],
)


def test_transition_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_transition_cube_sql(**ARGS))


def test_uses_pageview_rows_as_screens():
    sql = build_transition_cube_sql(**ARGS)
    assert "action_type = 'Pageview'" in sql


def test_screens_outside_the_dictionary_fold_into_other():
    sql = build_transition_cube_sql(**ARGS)
    assert "'/other'" in sql
    assert "'top/홈탭_진입'" in sql


def test_adds_explicit_start_and_exit_states():
    sql = build_transition_cube_sql(**ARGS)
    assert "'START'" in sql
    assert "'EXIT'" in sql


def test_orders_events_within_a_session():
    # 한정자가 없으면 screens/kept 양쪽에 uuid,suid 가 있어 "Ambiguous reference" 로 죽는다.
    sql = build_transition_cube_sql(**ARGS)
    assert "PARTITION BY s.uuid, s.suid" in sql
    assert "ORDER BY s.ts" in sql


def test_emits_from_to_cnt_and_duration():
    sql = build_transition_cube_sql(**ARGS)
    for col in ("from_state", "to_state", "cnt", "dur_sum", "dur_n"):
        assert col in sql


def test_reads_dwell_from_usage_rows_not_pageview_rows():
    # Pageview 행의 usage.duration 은 비NULL 0건이다. 화면 신호만 읽으면 dur_sum 이 죽는다.
    sql = build_transition_cube_sql(**ARGS)
    assert "action_kind = 'UsagePage'" in sql
    assert "CASE WHEN action_type = 'Usage'" in sql
    # 원천은 밀리초다. 나누지 않으면 체류가 1000배로 나온다.
    assert "usage_duration_ms / 1000.0" in sql


def test_counts_measured_visits_so_coverage_is_visible():
    # dur_sum / cnt 는 커버리지만큼 축소된 틀린 값이다. dur_n 이 있어야 나눌 수 있다.
    sql = build_transition_cube_sql(**ARGS)
    assert "count(e.dwell_sum) AS dur_n" in sql


def test_start_edges_carry_no_dwell():
    # START 에 첫 화면 체류를 붙이면 같은 체류가 두 엣지에 들어간다.
    sql = build_transition_cube_sql(**ARGS)
    start_row = sql[sql.index("'START' AS from_state"):]
    assert "CAST(NULL AS double)" in start_row[:200]


def test_keeps_only_sessions_starting_on_the_target_date():
    sql = build_transition_cube_sql(**ARGS)
    assert "'2026-07-27'" in sql


def test_screen_list_escapes_single_quotes():
    args = {**ARGS, "screens": ["top/o'hara"]}
    assert "o''hara" in build_transition_cube_sql(**args)


def test_attribution_is_identical_to_the_session_cube():
    """두 큐브는 **같은** 귀속 절을 써야 한다 — 문자열이 아니라 공유 헬퍼로 강제한다.

    계획 초안은 `kept` 를 `screens`(Pageview 행)에서 뽑았다. `top` 이벤트의 90%가
    비-Pageview 라 대부분의 세션은 비-Pageview 로 시작하고, 그러면 같은 세션이
    session 큐브와 transition 큐브에서 서로 다른 날짜·daypart 버킷에 앉는다.
    """
    from analytics.cube.sql import _first_event_attribution, build_session_cube_sql

    clause = _first_event_attribution(ARGS["date"])
    session_sql = build_session_cube_sql(
        **{k: v for k, v in ARGS.items() if k != "screens"}
    )
    assert clause in session_sql
    assert clause in build_transition_cube_sql(**ARGS)


def test_sessions_are_attributed_before_screens_are_filtered():
    # 귀속의 원천은 ev 여야 한다. screens 에서 귀속하면 첫 화면 = 첫 이벤트로 착각한다.
    sql = build_transition_cube_sql(**ARGS)
    kept = sql[sql.index("kept AS ("):]
    kept = kept[: kept.index("),")]
    assert "FROM ev" in kept
    assert "FROM screens" not in kept

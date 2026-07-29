from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import QUALITY_CHECKS, build_quality_cube_sql

ARGS = dict(
    events_table="bigdata_omega_common_iceberg.axz_tiara.all_tiara_n",
    date="2026-07-27",
    window_dates=["2026-07-26", "2026-07-27", "2026-07-28"],
    services=["top", "media"],
)


def test_quality_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_quality_cube_sql(**ARGS))


def test_declares_the_checks_from_the_spec():
    assert QUALITY_CHECKS == (
        "null_action_name",
        "pageview_null_kind",
        "screen_other_ratio",
        "session_no_screen",
        "page_name_ambiguous",
        "session_span_exceeds_timeout",
        "screen_without_dwell",
        "exit_without_appexit",
    )


def test_every_check_appears_in_the_sql():
    sql = build_quality_cube_sql(**ARGS)
    for check in QUALITY_CHECKS:
        assert f"'{check}'" in sql


def test_emits_check_name_violated_total():
    sql = build_quality_cube_sql(**ARGS)
    for col in ("check_name", "violated", "total"):
        assert f"AS {col}" in sql


def test_groups_by_service_code_so_per_service_variance_is_visible():
    sql = build_quality_cube_sql(**ARGS)
    assert "service_code" in sql


def test_does_not_apply_the_invalid_filter_because_it_measures_quality():
    sql = build_quality_cube_sql(**ARGS)
    assert "tag.is_invalid, '0') <> '1'" not in sql


def test_session_checks_use_the_same_attribution_as_the_other_cubes():
    """세션 검사는 3파티션 창 + 첫 이벤트 귀속을 써야 한다.

    단일 파티션만 읽으면 자정을 넘긴 세션의 span 이 절단되어
    `session_span_exceeds_timeout` 이 **감시해야 할 바로 그 세션들에 눈이 먼다.**
    """
    from analytics.cube.sql import _first_event_attribution

    sql = build_quality_cube_sql(**ARGS)
    assert _first_event_attribution(ARGS["date"]) in sql
    assert "date_id IN ('2026-07-26', '2026-07-27', '2026-07-28')" in sql


def test_exit_check_counts_only_app_sessions():
    # 웹에는 종료 이벤트가 없다. 섞으면 이 검사가 "웹 비중"을 재게 된다.
    sql = build_quality_cube_sql(**ARGS)
    assert "app_events > 0" in sql
    assert "action_kind = 'AppExit'" in sql


def test_row_checks_are_confined_to_the_target_partition():
    # 창은 세션 검사용이다. 행 단위 검사까지 3일치를 세면 분모가 3배로 부푼다.
    sql = build_quality_cube_sql(**ARGS)
    assert "day AS (" in sql
    assert "FROM day" in sql

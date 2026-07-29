from analytics.cube.axes import CORE_AXIS_NAMES
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import build_session_cube_sql

EVENTS = "bigdata_omega_common_iceberg.axz_tiara.all_tiara_n"
DEM = "hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2"
ARGS = dict(
    events_table=EVENTS,
    demography_table=DEM,
    date="2026-07-27",
    window_dates=["2026-07-26", "2026-07-27", "2026-07-28"],
    services=["top", "media"],
    versions=["9.5.1", "9.5.0"],
)


def test_session_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_session_cube_sql(**ARGS))


def test_reads_the_previous_day_too_so_sessions_are_not_double_counted():
    # D-1 을 안 읽으면 D-1 에 시작해 D 로 넘어온 세션의 꼬리를 D 빌드가 새 세션으로 센다.
    sql = build_session_cube_sql(**ARGS)
    assert "date_id IN ('2026-07-26', '2026-07-27', '2026-07-28')" in sql


def test_attribution_date_is_not_taken_from_the_window():
    # HAVING 의 날짜는 창의 어느 끝도 아니라 귀속 대상 날짜여야 한다.
    sql = build_session_cube_sql(**ARGS)
    assert "date('2026-07-27')" in sql
    assert "date('2026-07-26')" not in sql
    assert "date('2026-07-28')" not in sql


def test_keeps_only_sessions_starting_on_the_target_date():
    sql = build_session_cube_sql(**ARGS)
    assert "HAVING" in sql
    assert "min(ts)" in sql
    assert "'2026-07-27'" in sql


def test_attributes_axes_by_first_event():
    sql = build_session_cube_sql(**ARGS)
    assert "min_by(" in sql


def test_emits_every_core_axis():
    sql = build_session_cube_sql(**ARGS)
    for axis in CORE_AXIS_NAMES:
        assert axis in sql


def test_emits_the_session_measures():
    sql = build_session_cube_sql(**ARGS)
    for measure in ("sessions", "uv", "pv", "events", "duration_sum"):
        assert f"AS {measure}" in sql


def test_uses_grouping_sets_so_uv_is_never_summed_downstream():
    sql = build_session_cube_sql(**ARGS)
    assert "GROUPING SETS" in sql


def test_joins_demography_with_a_left_join():
    sql = build_session_cube_sql(**ARGS)
    assert "LEFT JOIN" in sql
    assert DEM in sql


def test_counts_distinct_uuid_for_uv():
    sql = build_session_cube_sql(**ARGS)
    assert "count(DISTINCT" in sql


def test_period_is_the_build_date_not_the_partition_of_the_first_event():
    """`period` 는 귀속일과 반드시 같아야 한다.

    `min_by(period, ts)` 로 두면 첫 이벤트가 **쓰인 파티션**(`date_id`)이 되는데, 귀속은
    첫 이벤트의 `access_time` 날짜로 한다. 실측 0.0919% 가 어긋났고 D+1 쪽으로 치우쳤다.
    그러면 14일치를 이어붙여 `period` 로 묶을 때 한 period 에 롤업 행이 둘 나와서,
    합산하면 조용히 2배가 된다.
    """
    sql = build_session_cube_sql(**ARGS)
    assert "'2026-07-27' AS period" in sql
    assert "min_by(period" not in sql


def test_the_other_axes_still_come_from_the_first_event():
    sql = build_session_cube_sql(**ARGS)
    for axis in ("service_type", "os", "gender", "age_band", "daypart", "app_version"):
        assert f"min_by({axis}, ts)" in sql

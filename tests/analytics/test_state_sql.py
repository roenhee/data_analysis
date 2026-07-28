from analytics.cube.guard import assert_safe_sql
from analytics.cube.state_sql import (
    build_layer1_count_sql,
    build_layer2_count_sql,
    build_screen_count_sql,
    build_version_count_sql,
)

WINDOW = ("2026-07-01", "2026-07-31")
SERVICES = ["top", "media"]
TABLE = "bigdata_omega_common_iceberg.axz_tiara.all_tiara_n"


def test_screen_count_sql_is_pruned_and_safe():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert_safe_sql(sql)


def test_screen_count_sql_selects_value_and_cnt():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "AS value" in sql
    assert "AS cnt" in sql


def test_screen_count_sql_uses_pageview_only():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "action.type = 'Pageview'" in sql


def test_screen_value_is_service_slash_name():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "c_service_code" in sql and "'/'" in sql


def test_window_bounds_are_inclusive_on_date_id():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "date_id BETWEEN '2026-07-01' AND '2026-07-31'" in sql


def test_services_are_quoted_into_an_in_list():
    sql = build_screen_count_sql(TABLE, WINDOW, SERVICES)
    assert "c_service_code IN ('top', 'media')" in sql


def test_layer1_and_layer2_sql_are_pruned_and_safe():
    for builder in (build_layer1_count_sql, build_layer2_count_sql):
        assert_safe_sql(builder(TABLE, WINDOW, SERVICES))


def test_layer2_value_is_layer1_gt_layer2():
    sql = build_layer2_count_sql(TABLE, WINDOW, SERVICES)
    assert "'>'" in sql


def test_version_count_sql_is_pruned_and_safe():
    assert_safe_sql(build_version_count_sql(TABLE, WINDOW, SERVICES))


def test_service_list_escapes_single_quotes():
    sql = build_screen_count_sql(TABLE, WINDOW, ["o'hara"])
    assert "o''hara" in sql

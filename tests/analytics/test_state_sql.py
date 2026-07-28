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


def test_every_builder_emits_the_value_cnt_contract():
    # apply_cut 이 소비하는 컬럼 쌍이므로 네 빌더 모두 지켜야 한다.
    for builder in (
        build_screen_count_sql,
        build_layer1_count_sql,
        build_layer2_count_sql,
        build_version_count_sql,
    ):
        sql = builder(TABLE, WINDOW, SERVICES)
        assert "AS value" in sql, builder.__name__
        assert "AS cnt" in sql, builder.__name__


def test_reversed_window_is_rejected():
    # 뒤집힌 구간은 조용히 0행을 내므로 빈 사전이 만들어진다.
    import pytest

    with pytest.raises(ValueError, match="precedes start"):
        build_screen_count_sql(TABLE, ("2026-07-31", "2026-07-01"), SERVICES)


def test_base_filters_match_the_events_source_config():
    """`sources.json` 의 필터가 바뀌면 여기도 따라가야 한다 — 조용한 드리프트 방지."""
    import json
    from pathlib import Path

    from analytics.cube.state_sql import BASE_FILTERS

    raw = json.loads(Path("examples/config/sources.json").read_text())
    events = next(s for s in raw if s["id"] == "events")
    assert list(BASE_FILTERS) == events["filters"]

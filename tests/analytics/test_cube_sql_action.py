"""`action` 큐브 SQL 의 문자열 검사. 의미는 `test_action_semantics.py` 가 본다."""
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import build_action_cube_sql

ARGS = dict(
    events_table="bigdata_omega_common_iceberg.axz_tiara.all_tiara_n",
    demography_table="hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2",
    date="2026-07-27",
    window_dates=["2026-07-26", "2026-07-27", "2026-07-28"],
    services=["top"],
    versions=["9.5.1"],
    screens=["top/홈탭_진입"],
    layer1=["home_main"],
    layer2=["home_main>SEARCH"],
)


def test_action_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_action_cube_sql(**ARGS))


def test_attribution_is_identical_to_the_session_cube():
    """귀속이 갈라지면 같은 세션이 큐브마다 다른 날짜·축 버킷에 앉는다."""
    from analytics.cube.sql import _first_event_attribution

    assert _first_event_attribution(ARGS["date"]) in build_action_cube_sql(**ARGS)


def test_the_screen_expression_is_identical_to_the_transition_cube():
    """두 큐브를 조인해야 하므로 **같은 식**이어야 한다. `common.page` 는 쓰지 않는다."""
    from analytics.cube.sql import build_transition_cube_sql

    action = build_action_cube_sql(**ARGS)
    transition = build_transition_cube_sql(
        **{k: v for k, v in ARGS.items() if k not in ("layer1", "layer2")}
    )
    screen_expr = (
        "service_code || '/' || coalesce(nullif(trim(action_name), ''), '(none)')"
    )
    assert screen_expr in action and screen_expr in transition
    assert "'/other'" in action


def test_clicks_are_selected_by_the_slot_coordinate_not_the_action_kind():
    """실측: `NOT IN ('Pageview','Usage')` 는 31.2억 행인데 상호작용은 5.5% 다."""
    sql = build_action_cube_sql(**ARGS)
    assert "nullif(trim(layer1), '') IS NOT NULL" in sql
    assert "NOT IN ('Pageview', 'Usage')" not in sql


def test_it_reuses_the_visit_index_to_bind_a_click_to_a_screen():
    sql = build_action_cube_sql(**ARGS)
    assert "sum(is_screen) OVER" in sql
    assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql


def test_a_click_before_the_first_screen_is_attributed_to_start():
    """버리면 분모가 줄어든다. 전이 큐브가 쓰는 표기를 그대로 쓴다."""
    assert "coalesce(v.state, 'START')" in build_action_cube_sql(**ARGS)


def test_emits_the_action_layer_columns():
    sql = build_action_cube_sql(**ARGS)
    for col in ("screen", "action_kind", "layer1", "layer2", "cnt"):
        assert col in sql


def test_layer_values_outside_the_dictionary_fold_into_other():
    sql = build_action_cube_sql(**ARGS)
    assert "'home_main'" in sql
    assert "'other'" in sql


def test_layer_list_escapes_single_quotes():
    args = {**ARGS, "layer1": ["o'hara"]}
    assert "o''hara" in build_action_cube_sql(**args)


def test_empty_dictionaries_still_produce_runnable_sql():
    args = {**ARGS, "layer1": [], "layer2": [], "screens": []}
    assert_safe_sql(build_action_cube_sql(**args))

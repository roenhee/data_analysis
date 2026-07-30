"""`cond_transition` 큐브 SQL 의 문자열 검사. 의미는 의미 테스트가 본다."""
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import COND_AXIS_NAMES, build_cond_transition_cube_sql

ARGS = dict(
    events_table="bigdata_omega_common_iceberg.axz_tiara.all_tiara_n",
    demography_table="hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2",
    date="2026-07-27",
    window_dates=["2026-07-26", "2026-07-27", "2026-07-28"],
    services=["top"],
    versions=["9.5.1"],
    screens=["top/홈탭_진입", "top/콘텐츠탭_진입"],
)


def test_cond_transition_sql_is_pruned_and_safe():
    assert_safe_sql(build_cond_transition_cube_sql(**ARGS))


def test_uses_only_the_four_reduced_axes():
    """7축이면 하루 최대 171만 행(전이쌍 3,604 × kind 8)이라 코어보다 무거워진다."""
    assert COND_AXIS_NAMES == ("period", "service_type", "os", "app_version")
    tail = build_cond_transition_cube_sql(**ARGS).split("GROUP BY")[-1]
    for axis in COND_AXIS_NAMES:
        assert axis in tail
    assert "gender" not in tail
    assert "age_band" not in tail
    assert "daypart" not in tail


def test_attribution_is_identical_to_the_session_cube():
    from analytics.cube.sql import _first_event_attribution

    assert _first_event_attribution(ARGS["date"]) in build_cond_transition_cube_sql(
        **ARGS
    )


def test_the_click_filter_is_the_same_as_the_action_cube():
    """갈리면 두 큐브의 `cnt` 합이 안 맞고 그걸 "다중 행동" 으로 오해한다."""
    sql = build_cond_transition_cube_sql(**ARGS)
    assert "nullif(trim(layer1), '') IS NOT NULL" in sql
    assert "NOT IN ('Pageview', 'Usage')" not in sql


def test_the_screen_expression_is_the_same_as_the_transition_cube():
    sql = build_cond_transition_cube_sql(**ARGS)
    assert (
        "service_code || '/' || coalesce(nullif(trim(action_name), ''), '(none)')"
        in sql
    )


def test_emits_from_state_action_kind_to_state():
    sql = build_cond_transition_cube_sql(**ARGS)
    for col in ("from_state", "action_kind", "to_state", "cnt"):
        assert col in sql


def test_reuses_the_visit_index_to_bind_clicks_to_a_screen():
    sql = build_cond_transition_cube_sql(**ARGS)
    assert "sum(is_screen) OVER" in sql
    assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql


def test_a_transition_with_no_click_is_labelled_apart_from_a_click_with_no_kind():
    """**두 개는 다른 것이다.** 실측 클릭 집합의 절반이 `action.kind` 가 없어서, 둘을 같은
    라벨에 넣으면 "행동 없이 넘어간 전이" 와 "종류 모를 클릭" 이 큰 덩어리로 뭉개진다.
    """
    sql = build_cond_transition_cube_sql(**ARGS)
    assert "'(no_click)'" in sql
    assert "'(none)'" in sql


def test_start_edges_are_emitted_so_early_clicks_have_a_home():
    """첫 화면 이전 클릭은 `START -> 첫화면` 엣지에 붙는다 — 전이 큐브와 같은 표기."""
    assert "'START'" in build_cond_transition_cube_sql(**ARGS)


def test_a_transition_to_nowhere_becomes_exit():
    assert "'EXIT'" in build_cond_transition_cube_sql(**ARGS)


def test_empty_screens_still_produce_runnable_sql():
    assert_safe_sql(build_cond_transition_cube_sql(**{**ARGS, "screens": []}))

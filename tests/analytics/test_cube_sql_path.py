"""`path` 큐브 SQL 의 문자열 검사. 의미는 의미 테스트가 본다."""
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import PATH_LENGTHS, PATH_TOP_N, build_path_cube_sql

ARGS = dict(
    events_table="bigdata_omega_common_iceberg.axz_tiara.all_tiara_n",
    demography_table="hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2",
    date="2026-07-27",
    window_dates=["2026-07-26", "2026-07-27", "2026-07-28"],
    services=["top"],
    versions=["9.5.1"],
    screens=["top/홈탭_진입", "top/콘텐츠탭_진입"],
)


def test_path_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_path_cube_sql(**ARGS))


def test_attribution_is_identical_to_the_session_cube():
    from analytics.cube.sql import _first_event_attribution

    assert _first_event_attribution(ARGS["date"]) in build_path_cube_sql(**ARGS)


def test_emits_n_and_path_and_cnt():
    sql = build_path_cube_sql(**ARGS)
    for col in ("n", "path", "cnt", "distinct_dropped"):
        assert col in sql


def test_covers_n_from_three_to_five():
    assert PATH_LENGTHS == (3, 4, 5)
    sql = build_path_cube_sql(**ARGS)
    for n in PATH_LENGTHS:
        assert f"{n} AS n" in sql


def test_it_builds_ngrams_with_lead_not_array_slicing():
    """**방언 차이를 피하려고 배열을 쓰지 않는다.**

    Trino `slice(arr, start, 길이)` 와 DuckDB `list_slice(arr, begin, 끝인덱스)` 는 세 번째
    인자의 뜻이 다르다. 그대로 옮기면 n-gram 길이가 조용히 틀리고, 그러면 의미 테스트가
    프로덕션과 다른 것을 검증한다. `lead()` 와 `||` 만 쓰면 두 방언에서 같다.
    """
    sql = build_path_cube_sql(**ARGS)
    assert "lead(state" in sql
    for banned in ("slice(", "sequence(", "array_join", "array_agg", "UNNEST"):
        assert banned not in sql, banned


def test_keeps_the_top_n_per_segment_and_n():
    sql = build_path_cube_sql(**ARGS)
    assert PATH_TOP_N == 200
    assert "row_number() OVER" in sql
    assert str(PATH_TOP_N) in sql


def test_the_rank_has_a_deterministic_tie_break():
    """`ORDER BY cnt DESC` 만이면 200위와 201위가 실행마다 바뀌어 큐브가 재현되지 않는다."""
    assert "ORDER BY cnt DESC, path" in build_path_cube_sql(**ARGS)


def test_emits_an_other_row_for_the_truncated_tail():
    """컷을 조용히 하면 소비자가 상위 200을 전수로 읽는다 — `dur_n`·`/other` 와 같은 부류."""
    sql = build_path_cube_sql(**ARGS)
    assert "'(other)'" in sql
    assert "distinct_dropped" in sql


def test_empty_screens_still_produce_runnable_sql():
    assert_safe_sql(build_path_cube_sql(**{**ARGS, "screens": []}))

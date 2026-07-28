import pytest

from analytics.cube.guard import GuardError, assert_safe_sql

PRUNED = """
SELECT count(*) FROM t
WHERE date_id IN ('2026-07-27')
  AND c_service_code IN ('top')
"""


def test_pruned_sql_passes():
    assert_safe_sql(PRUNED) is None


def test_missing_date_id_is_rejected():
    sql = "SELECT count(*) FROM t WHERE c_service_code IN ('top')"
    with pytest.raises(GuardError, match="date_id"):
        assert_safe_sql(sql)


def test_missing_service_code_is_rejected():
    sql = "SELECT count(*) FROM t WHERE date_id IN ('2026-07-27')"
    with pytest.raises(GuardError, match="c_service_code"):
        assert_safe_sql(sql)


def test_not_in_is_rejected_because_null_poisons_it():
    sql = PRUNED + " AND action.name NOT IN ('a')"
    with pytest.raises(GuardError, match="NOT IN"):
        assert_safe_sql(sql)


def test_not_in_detection_is_case_insensitive_and_whitespace_tolerant():
    sql = PRUNED + " AND action.name not   in ('a')"
    with pytest.raises(GuardError, match="NOT IN"):
        assert_safe_sql(sql)


def test_not_null_is_not_mistaken_for_not_in():
    sql = PRUNED + " AND action.name IS NOT NULL"
    assert assert_safe_sql(sql) is None


def test_pruning_column_only_in_the_select_list_is_rejected():
    # 가장 현실적인 실수: SELECT 에는 넣고 WHERE 에는 빼먹는다.
    sql = "SELECT date_id, count(*) FROM t WHERE c_service_code IN ('top')"
    with pytest.raises(GuardError, match="date_id"):
        assert_safe_sql(sql)


def test_pruning_column_only_in_a_comment_is_rejected():
    sql = "-- date_id filter TODO\nSELECT count(*) FROM t WHERE c_service_code IN ('top')"
    with pytest.raises(GuardError, match="date_id"):
        assert_safe_sql(sql)


def test_longer_identifier_containing_the_column_is_not_accepted():
    sql = "SELECT 1 FROM t WHERE my_date_id_backup = '1' AND c_service_code IN ('top')"
    with pytest.raises(GuardError, match="date_id"):
        assert_safe_sql(sql)


def test_sql_without_a_where_clause_is_rejected():
    with pytest.raises(GuardError):
        assert_safe_sql("SELECT count(*) FROM t")


def test_column_matching_is_case_insensitive():
    sql = "SELECT 1 FROM t WHERE DATE_ID IN ('x') AND C_SERVICE_CODE IN ('y')"
    assert assert_safe_sql(sql) is None


def test_ne_all_is_banned_like_not_in():
    sql = PRUNED + " AND action.name <> ALL (ARRAY['a'])"
    with pytest.raises(GuardError, match="NOT IN"):
        assert_safe_sql(sql)


def test_known_limitation_subquery_only_constraint_still_passes():
    """파서 없이는 못 잡는 알려진 한계를 고정한다.

    바깥 스캔은 안 잘리지만 통과한다. 이 테스트가 깨지면 가드가 더 엄격해진 것이므로
    한계 문서를 함께 갱신한다.
    """
    sql = (
        "SELECT 1 FROM t WHERE date_id IN ('x') "
        "AND x IN (SELECT c_service_code FROM other)"
    )
    assert assert_safe_sql(sql) is None

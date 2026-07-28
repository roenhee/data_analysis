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

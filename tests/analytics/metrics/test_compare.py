import pandas as pd
import pytest

from analytics.metrics.compare import (
    ConfoundedComparisonError,
    comparable_dates,
    restrict_to_comparable,
)


def _cube(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [{"period": p, "app_version": v, "cnt": c} for p, v, c in rows]
    )


FULL = _cube([
    ("2026-07-25", "9.5.0", 100),
    ("2026-07-26", "9.5.0", 100),
    ("2026-07-27", "9.5.0", 100),
    ("2026-07-26", "9.5.1", 10),
    ("2026-07-27", "9.5.1", 90),
])


def test_comparable_dates_are_the_intersection():
    assert comparable_dates(FULL, "app_version", "9.5.1", "9.5.0") == [
        "2026-07-26", "2026-07-27",
    ]


def test_no_overlap_is_refused_rather_than_returning_a_number():
    """겹치는 날짜가 없으면 델타는 버전 차이가 아니라 날짜 차이다.

    실측: 9.5.1 은 07-26 부터, 9.5.0 은 07-14 부터 존재한다. 14일 전체로 비교하면
    기대 걸음 수가 +2.9% 로 나오는데, 겹치는 날짜로만 재면 -0.2% 다. 부호가 뒤집힌다.
    """
    cube = _cube([("2026-07-20", "9.4.0", 100), ("2026-07-27", "9.5.1", 100)])
    with pytest.raises(ConfoundedComparisonError, match="no overlapping"):
        comparable_dates(cube, "app_version", "9.5.1", "9.4.0")


def test_a_missing_version_is_refused():
    with pytest.raises(ConfoundedComparisonError, match="9.9.9"):
        comparable_dates(FULL, "app_version", "9.9.9", "9.5.0")


def test_restrict_keeps_only_the_overlapping_dates_and_the_two_versions():
    got = restrict_to_comparable(FULL, "app_version", "9.5.1", "9.5.0")
    assert set(got["period"]) == {"2026-07-26", "2026-07-27"}
    assert set(got["app_version"]) == {"9.5.0", "9.5.1"}
    assert len(got) == 4


def test_restrict_drops_the_non_overlapping_days_of_the_older_version():
    got = restrict_to_comparable(FULL, "app_version", "9.5.1", "9.5.0")
    assert "2026-07-25" not in set(got["period"])


def test_a_thin_overlap_is_reported_so_the_caller_can_judge():
    # 하루만 겹치면 요일 효과를 못 걷어낸다. 막지는 않되 날짜 수는 보이게 한다.
    cube = _cube([("2026-07-27", "9.5.0", 100), ("2026-07-27", "9.5.1", 10)])
    assert comparable_dates(cube, "app_version", "9.5.1", "9.5.0") == ["2026-07-27"]


def test_works_on_any_axis_not_just_app_version():
    cube = pd.DataFrame([
        {"period": "2026-07-27", "os": "android", "cnt": 1},
        {"period": "2026-07-27", "os": "ios", "cnt": 1},
        {"period": "2026-07-26", "os": "android", "cnt": 1},
    ])
    assert comparable_dates(cube, "os", "ios", "android") == ["2026-07-27"]

"""n-gram 경로. `(other)` 가 경로가 아니라 **컷의 크기**인 것이 요점이다."""
import pandas as pd
import pytest

from analytics.metrics.paths import OTHER_PATH, path_coverage, top_paths


def _paths() -> pd.DataFrame:
    return pd.DataFrame([
        {"n": 3, "path": "a>b>c", "cnt": 50, "distinct_dropped": 0},
        {"n": 3, "path": "a>b>d", "cnt": 30, "distinct_dropped": 0},
        {"n": 3, "path": OTHER_PATH, "cnt": 20, "distinct_dropped": 400},
        {"n": 4, "path": "a>b>c>d", "cnt": 10, "distinct_dropped": 0},
        {"n": 4, "path": OTHER_PATH, "cnt": 90, "distinct_dropped": 9000},
    ])


def test_top_paths_are_ranked_by_count():
    got = top_paths(_paths(), n=3)
    assert got["path"].tolist() == ["a>b>c", "a>b>d"]
    assert got["cnt"].is_monotonic_decreasing


def test_the_other_row_is_excluded_from_the_ranking():
    """`(other)` 는 경로가 아니라 컷의 크기다. 순위에 섞이면 1위가 될 수도 있다 —
    실측 픽스처의 n=4 가 정확히 그렇다(90 대 10).
    """
    assert OTHER_PATH not in set(top_paths(_paths(), n=4)["path"])


def test_the_share_is_out_of_the_uncut_total():
    """분모는 컷 이전 전체(`(other)` 포함)다. 상위 200 안에서만 정규화하면 부푼다."""
    got = top_paths(_paths(), n=3).set_index("path")
    assert got.loc["a>b>c", "share"] == pytest.approx(0.5)
    assert got.loc["a>b>d", "share"] == pytest.approx(0.3)


def test_coverage_is_the_share_the_top_paths_actually_cover():
    assert path_coverage(_paths(), n=3) == pytest.approx(0.8)
    assert path_coverage(_paths(), n=4) == pytest.approx(0.1)


def test_paths_of_different_n_are_never_pooled():
    """n=3 과 n=4 는 다른 모집단이다. 합치면 같은 방문이 여러 번 세어진다."""
    with pytest.raises(ValueError, match="one n at a time"):
        top_paths(_paths(), n=None)


def test_a_segment_whose_tail_dominates_is_flagged():
    """`(other)` 가 절반을 넘으면 상위 200 이 대표성을 잃는다."""
    assert top_paths(_paths(), n=4).attrs["tail_dominates"] is True
    assert top_paths(_paths(), n=3).attrs["tail_dominates"] is False


def test_the_dropped_path_count_is_reported_next_to_the_coverage():
    """커버리지 0.1 이 "200개가 꼬리 전부" 인지 "9,000개를 잘랐" 는지로 해석이 갈린다."""
    got = top_paths(_paths(), n=4)
    assert got.attrs["distinct_dropped"] == 9000
    assert got.attrs["coverage"] == pytest.approx(0.1)


def test_a_missing_n_raises_rather_than_returning_empty():
    with pytest.raises(KeyError, match="no rows for n"):
        top_paths(_paths(), n=5)


def test_a_segment_with_no_tail_reports_full_coverage():
    """컷에 안 걸린 세그먼트는 `(other)` 행이 없다 — 커버리지 1.0 이고 NaN 이 아니다."""
    clean = pd.DataFrame([
        {"n": 3, "path": "a>b>c", "cnt": 5, "distinct_dropped": 0},
    ])
    assert path_coverage(clean, n=3) == pytest.approx(1.0)
    got = top_paths(clean, n=3)
    assert got.attrs["distinct_dropped"] == 0
    assert got.attrs["tail_dominates"] is False

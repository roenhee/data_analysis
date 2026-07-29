import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis


def _edges(rows) -> pd.DataFrame:
    """`(from, to, cnt, dur_n, dur_sum)` 엣지."""
    return pd.DataFrame([
        {"period": "2026-07-27", "from_state": f, "to_state": t, "cnt": c,
         "dur_n": n, "dur_sum": float(s)}
        for f, t, c, n, s in rows
    ])


def _cubes(rows) -> CubeSet:
    return CubeSet(session=None, transition=_edges(rows), quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


# 방문 300 중 200 만 체류가 측정됐고 합이 2000초.
#   옳은 답 2000/200 = 10.0초 (측정된 방문의 조건부 평균)
#   틀린 답 2000/300 =  6.67초 (커버리지 2/3 만큼 축소) — 실측에서 밟은 값이다
TWO_THIRDS = [("A", "B", 200, 130, 1300.0), ("A", "EXIT", 100, 70, 700.0),
              ("B", "EXIT", 300, 300, 1500.0)]


def test_divides_by_measured_visits_not_transitions():
    """dur_sum/cnt 는 커버리지만큼 축소된다 — 실측 6.67초 vs 10.0초."""
    got = get_analysis("screen_dwell_rank")(_cubes(TWO_THIRDS))
    row = got.frame.set_index("state").loc["A"]
    assert row["seconds_per_visit"] == pytest.approx(10.0)
    assert row["visits"] == 300
    assert row["measured_visits"] == 200


def test_coverage_travels_with_the_value():
    got = get_analysis("screen_dwell_rank")(_cubes(TWO_THIRDS))
    row = got.frame.set_index("state").loc["A"]
    assert row["coverage"] == pytest.approx(200 / 300)
    assert row["dwell_definition"] == "usagepage_seconds"


def test_a_screen_with_no_measured_dwell_is_nan_not_zero():
    """0초 머물렀다와 얼마나 머물렀는지 모른다는 다른 말이다."""
    rows = TWO_THIRDS + [("C", "EXIT", 50, 0, 0.0)]
    got = get_analysis("screen_dwell_rank")(_cubes(rows))
    assert pd.isna(got.frame.set_index("state").loc["C", "seconds_per_visit"])


def test_the_rank_puts_the_longest_screen_first():
    got = get_analysis("screen_dwell_rank")(_cubes(TWO_THIRDS))
    assert got.frame["state"].tolist() == ["A", "B"]


def test_headline_carries_the_weighted_mean_dwell():
    """측정된 방문으로 가중한다 = 전체 dur_sum / 전체 dur_n.

    화면끼리 단순 평균하면 (10.0 + 5.0)/2 = 7.5 가 나온다. 옳은 값은 3500/500 = 7.0 이다.
    """
    got = get_analysis("screen_dwell_rank")(_cubes(TWO_THIRDS))
    assert got.headline["mean_seconds_per_visit"] == pytest.approx(7.0)


def test_headline_carries_coverage_so_a_comparison_shows_it_drifting():
    """세그먼트끼리 커버리지가 다르면 조건부 평균은 애초에 비교가 안 된다.

    headline 에 넣으면 `compare` 가 그 델타를 자동으로 함께 낸다.
    """
    got = get_analysis("screen_dwell_rank")(_cubes(TWO_THIRDS))
    assert got.headline["dwell_coverage"] == pytest.approx(500 / 600)


def test_the_envelope_warns_when_dwell_coverage_is_below_half():
    """커버리지 절반 미만이면 조건부 평균이라도 대표성이 약하다. 막지 않고 경고한다."""
    thin = _cubes([("A", "B", 300, 100, 1000.0), ("B", "EXIT", 300, 100, 500.0)])
    got = get_analysis("screen_dwell_rank")(thin)
    warned = [w for w in got.envelope["warnings"]
              if w["check_name"] == "low_dwell_coverage"]
    assert len(warned) == 1
    assert warned[0]["coverage"] == pytest.approx(200 / 600)
    # 막지 않는다: 값은 그대로 나온다.
    assert got.headline["mean_seconds_per_visit"] == pytest.approx(7.5)


def test_no_warning_when_coverage_clears_the_half():
    got = get_analysis("screen_dwell_rank")(_cubes(TWO_THIRDS))
    names = [w["check_name"] for w in got.envelope["warnings"]]
    assert "low_dwell_coverage" not in names

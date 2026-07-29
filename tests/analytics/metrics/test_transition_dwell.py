import pandas as pd
import pytest

from analytics.metrics.descriptive import screen_dwell


def _edges() -> pd.DataFrame:
    return pd.DataFrame([
        {"from_state": "top/A", "to_state": "top/B", "cnt": 100,
         "dur_sum": 600.0, "dur_n": 60},
        {"from_state": "top/A", "to_state": "EXIT", "cnt": 50,
         "dur_sum": 400.0, "dur_n": 40},
        {"from_state": "top/B", "to_state": "EXIT", "cnt": 20,
         "dur_sum": 0.0, "dur_n": 0},
        {"from_state": "START", "to_state": "top/A", "cnt": 150,
         "dur_sum": 0.0, "dur_n": 0},
    ])


def test_mean_dwell_divides_by_measured_visits_not_by_transitions():
    # top/A: dur_sum 1000 / dur_n 100 = 10.0 초.
    # cnt 150 으로 나누면 6.67 초 — 커버리지만큼 축소된 틀린 값.
    got = screen_dwell(_edges()).set_index("state")
    assert got.loc["top/A", "seconds_per_visit"] == pytest.approx(10.0)


def test_coverage_is_reported_next_to_the_value():
    got = screen_dwell(_edges()).set_index("state")
    assert got.loc["top/A", "coverage"] == pytest.approx(100 / 150)


def test_a_screen_with_no_measured_dwell_yields_nan_not_zero():
    # 0 으로 내면 "체류가 0초"와 "체류를 모른다"가 구분되지 않는다.
    got = screen_dwell(_edges()).set_index("state")
    assert pd.isna(got.loc["top/B", "seconds_per_visit"])
    assert got.loc["top/B", "coverage"] == pytest.approx(0.0)


def test_visits_are_the_sum_of_outgoing_transitions():
    got = screen_dwell(_edges()).set_index("state")
    assert int(got.loc["top/A", "visits"]) == 150


def test_start_and_exit_are_not_screens_so_they_have_no_dwell_row():
    states = set(screen_dwell(_edges())["state"])
    assert "EXIT" not in states
    assert "START" not in states


def test_dwell_definition_is_labelled_differently_from_the_session_cube():
    # 세션 큐브의 session_span_seconds 와 섞이면 안 된다.
    got = screen_dwell(_edges())
    assert set(got["dwell_definition"]) == {"usagepage_seconds"}

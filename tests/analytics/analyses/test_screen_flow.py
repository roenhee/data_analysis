import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

# 손으로 푼 체인. START -> A, A 는 60% B / 40% 이탈, B 는 전부 이탈.
#   exit_prob   A 0.4        B 1.0
#   expected    A 1 + 0.6 = 1.6   B 1.0
#   방문(나가는 cnt)  A 100  B 60
#   방문 가중 평균 걸음 수 = (100*1.6 + 60*1.0) / 160 = 1.375
#   방문 가중 이탈확률   = (40 + 60) / 160 = 0.625
CHAIN = [("START", "A", 100, 0), ("A", "B", 60, 40), ("A", "EXIT", 40, 17),
         ("B", "EXIT", 60, 30)]


def _edges(rows) -> pd.DataFrame:
    return pd.DataFrame([
        {"period": "2026-07-27", "from_state": f, "to_state": t, "cnt": c,
         "dur_n": n, "dur_sum": float(n) * 10.0}
        for f, t, c, n in rows
    ])


def _cubes(rows=CHAIN) -> CubeSet:
    return CubeSet(session=None, transition=_edges(rows), quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def test_frame_has_one_row_per_screen():
    got = get_analysis("screen_flow")(_cubes())
    assert got.frame["state"].tolist() == ["A", "B"]


def test_columns_cover_exit_stationary_and_expected_steps():
    got = get_analysis("screen_flow")(_cubes())
    assert {"exit_prob", "pi", "expected_steps", "p_reach_exit", "visits"} <= set(
        got.frame.columns
    )
    row = got.frame.set_index("state").loc["A"]
    assert row["exit_prob"] == pytest.approx(0.4)
    assert row["expected_steps"] == pytest.approx(1.6)
    assert row["visits"] == pytest.approx(100.0)


def test_headline_carries_mean_expected_steps_and_mean_exit_prob():
    """방문 가중이다 — 화면끼리 단순 평균하면 (1.6+1.0)/2 = 1.3 이 된다.

    세그먼트마다 등장하는 화면 집합이 달라지므로 단순 평균은 비교에 쓸 수 없다.
    """
    got = get_analysis("screen_flow")(_cubes())
    assert got.headline["mean_expected_steps"] == pytest.approx(1.375)
    assert got.headline["mean_exit_prob"] == pytest.approx(0.625)


def test_thin_cells_are_flagged_in_the_envelope_warnings():
    """엣지 셀의 cnt 중앙값은 9고 18.9%는 1이다 — 얇은 셀 경고가 붙어야 한다."""
    thin = _cubes(CHAIN + [("A", "C", 1, 1), ("C", "EXIT", 1, 1)])
    warnings = get_analysis("screen_flow")(thin).envelope["warnings"]
    thin_warning = [w for w in warnings if w["check_name"] == "thin_transition_cells"]
    assert len(thin_warning) == 1
    assert thin_warning[0]["single_observation_edges"] == 2


def test_a_chain_with_no_single_observation_edge_gets_no_thin_warning():
    names = [w["check_name"] for w in get_analysis("screen_flow")(
        _cubes()).envelope["warnings"]]
    assert "thin_transition_cells" not in names


def test_the_envelope_carries_dwell_coverage():
    got = get_analysis("screen_flow")(_cubes())
    # 화면 방문 160 중 체류가 측정된 87 = 54.4% (실측 57~69% 와 같은 자리)
    assert got.envelope["coverage"]["dwell"] == pytest.approx(87 / 160)


def test_an_empty_transition_frame_raises_rather_than_returning_zeros():
    empty = CubeSet(session=None, transition=_edges([]).iloc[0:0], quality=None,
                    state_dict_version="sd_abc", services=["top"],
                    requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="no transitions"):
        get_analysis("screen_flow")(empty)


def test_a_screen_that_cannot_reach_exit_is_infinite_not_a_plausible_number():
    """빠져나올 수 없는 곳이 있으면 기대 걸음 수는 발산한다. 유한한 값을 내면 거짓말이다."""
    trap = _cubes([("START", "A", 100, 0), ("A", "T", 50, 10), ("A", "EXIT", 50, 10),
                   ("T", "T", 50, 10)])
    got = get_analysis("screen_flow")(trap)
    frame = got.frame.set_index("state")
    assert frame.loc["T", "expected_steps"] == float("inf")
    assert frame.loc["A", "expected_steps"] == float("inf")
    # `compare` 가 보는 것은 frame 이 아니라 headline 이다. 여기서 유한한 수가 나오면
    # 델타는 그럴듯한 거짓말이 된다.
    assert got.headline["mean_expected_steps"] == float("inf")

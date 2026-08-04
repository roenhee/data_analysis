"""전이확률 히트맵 분석. `screen_pair_affinity` 의 PMI 와 달리 확률 그 자체를 낸다."""
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

# 손으로 푼 체인(test_screen_flow.py 와 같다). START -> A, A 는 60% B / 40% 이탈, B 는 전부 이탈.
#   P(START->A)=1.0  P(A->B)=0.6  P(A->EXIT)=0.4  P(B->EXIT)=1.0
CHAIN = [("START", "A", 100), ("A", "B", 60), ("A", "EXIT", 40), ("B", "EXIT", 60)]


def _edges(rows) -> pd.DataFrame:
    return pd.DataFrame([
        {"period": "2026-07-27", "from_state": f, "to_state": t, "cnt": c,
         "dur_n": c, "dur_sum": float(c) * 10.0}
        for f, t, c in rows
    ])


def _cubes(rows=CHAIN) -> CubeSet:
    return CubeSet(session=None, transition=_edges(rows), quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def test_frame_has_from_to_prob_and_cnt_columns():
    got = get_analysis("screen_transition")(_cubes())
    assert {"from_state", "to_state", "prob", "cnt"} <= set(got.frame.columns)


def test_probabilities_match_the_hand_solved_chain():
    got = get_analysis("screen_transition")(_cubes()).frame.set_index(
        ["from_state", "to_state"])
    assert got.loc[("START", "A"), "prob"] == pytest.approx(1.0)
    assert got.loc[("A", "B"), "prob"] == pytest.approx(0.6)
    assert got.loc[("A", "EXIT"), "prob"] == pytest.approx(0.4)
    assert got.loc[("B", "EXIT"), "prob"] == pytest.approx(1.0)
    assert got.loc[("A", "B"), "cnt"] == pytest.approx(60.0)


def test_probabilities_are_row_stochastic_over_observed_transitions():
    """각 from_state 의 관측된 to_state 들에 대한 prob 합은 1이어야 한다(행 확률 행렬)."""
    got = get_analysis("screen_transition")(_cubes()).frame
    sums = got.groupby("from_state")["prob"].sum()
    for from_state, total in sums.items():
        assert total == pytest.approx(1.0), from_state


def test_headline_carries_pair_and_state_counts():
    got = get_analysis("screen_transition")(_cubes())
    assert got.headline["pairs"] == pytest.approx(4.0)
    assert got.headline["states"] == pytest.approx(4.0)


def test_only_observed_transitions_are_emitted():
    """EXIT 는 나가는 관측이 없으므로 from_state 로 등장하지 않는다(자기루프를 내지 않는다)."""
    got = get_analysis("screen_transition")(_cubes())
    assert "EXIT" not in set(got.frame["from_state"])


def test_rows_are_sorted_by_cnt_descending():
    got = get_analysis("screen_transition")(_cubes())
    assert got.frame["cnt"].is_monotonic_decreasing


def test_viz_declares_the_heatmap_value_column_as_prob():
    """대시보드가 이 값으로 히트맵을 그린다 — cnt 가 아니라 prob."""
    got = get_analysis("screen_transition")(_cubes())
    assert got.viz == {"kind": "heatmap", "x": "from_state", "value": "prob"}


def test_thin_cells_are_flagged_in_the_envelope_warnings():
    thin = _cubes(CHAIN + [("A", "C", 1), ("C", "EXIT", 1)])
    warnings = get_analysis("screen_transition")(thin).envelope["warnings"]
    names = [w["check_name"] for w in warnings]
    assert "thin_transition_cells" in names


def test_an_empty_transition_frame_raises_rather_than_returning_zeros():
    empty = CubeSet(session=None, transition=_edges([]).iloc[0:0], quality=None,
                    state_dict_version="sd_abc", services=["top"],
                    requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="no transitions"):
        get_analysis("screen_transition")(empty)


def test_a_missing_transition_cube_raises():
    missing = CubeSet(session=None, transition=None, quality=None,
                      state_dict_version="sd_abc", services=["top"],
                      requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="needs the transition cube"):
        get_analysis("screen_transition")(missing)

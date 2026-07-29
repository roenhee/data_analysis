import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import (
    EXIT,
    START,
    exit_probabilities,
    stationary_distribution,
    transition_matrix,
)


def _edges(rows):
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


def test_exit_probability_is_the_share_of_departures_that_leave():
    P = transition_matrix(_edges([("A", "B", 3), ("A", EXIT, 1)]))
    got = exit_probabilities(P)
    assert got.loc[got["state"] == "A", "exit_prob"].iloc[0] == pytest.approx(0.25)


def test_exit_probability_omits_start_and_exit_themselves():
    P = transition_matrix(_edges([(START, "A", 1), ("A", EXIT, 1)]))
    assert set(exit_probabilities(P)["state"]) == {"A"}


def test_exit_probability_is_zero_when_nobody_leaves_from_there():
    P = transition_matrix(_edges([("A", "B", 1), ("B", EXIT, 1)]))
    got = exit_probabilities(P).set_index("state")["exit_prob"]
    assert got["A"] == pytest.approx(0.0)
    assert got["B"] == pytest.approx(1.0)


def test_a_single_screen_session_exits_from_that_screen_with_certainty():
    P = transition_matrix(_edges([(START, "A", 1), ("A", EXIT, 1)]))
    got = exit_probabilities(P).set_index("state")["exit_prob"]
    assert got["A"] == pytest.approx(1.0)


def test_stationary_sums_to_one():
    P = transition_matrix(_edges([("A", "B", 1), ("B", "A", 1), ("A", EXIT, 1)]))
    assert stationary_distribution(P)["pi"].sum() == pytest.approx(1.0)


def test_stationary_satisfies_pi_equals_pi_P():
    """불변식 π = πP. 화면 전용 부분체인 위에서 성립해야 한다."""
    P = transition_matrix(
        _edges([("A", "B", 3), ("A", "C", 1), ("B", "C", 2), ("C", "A", 4)])
    )
    got = stationary_distribution(P)
    states = list(got["state"])
    pi = got["pi"].to_numpy()
    idx = [P.states.index(s) for s in states]
    sub = P.matrix[np.ix_(idx, idx)]
    sub = sub / sub.sum(axis=1, keepdims=True)
    assert np.allclose(pi @ sub, pi, atol=1e-9)


def test_stationary_of_a_symmetric_two_state_chain_is_half_and_half():
    # 해석적 정답: A<->B 대칭이면 정상분포는 0.5/0.5.
    P = transition_matrix(_edges([("A", "B", 1), ("B", "A", 1)]))
    got = stationary_distribution(P).set_index("state")["pi"]
    assert got["A"] == pytest.approx(0.5)
    assert got["B"] == pytest.approx(0.5)


def test_stationary_of_a_biased_two_state_chain_matches_hand_calculation():
    # A->B 확률 1.0, B->A 확률 0.25, B->B 0.75.
    # π_A = 0.25/(1+0.25) = 0.2, π_B = 0.8
    P = transition_matrix(_edges([("A", "B", 4), ("B", "A", 1), ("B", "B", 3)]))
    got = stationary_distribution(P).set_index("state")["pi"]
    assert got["A"] == pytest.approx(0.2)
    assert got["B"] == pytest.approx(0.8)


def test_stationary_excludes_start_and_exit():
    P = transition_matrix(_edges([(START, "A", 1), ("A", "B", 1), ("B", EXIT, 1)]))
    assert START not in set(stationary_distribution(P)["state"])
    assert EXIT not in set(stationary_distribution(P)["state"])


def test_stationary_needs_at_least_one_screen_state():
    P = transition_matrix(_edges([(START, EXIT, 1)]))
    with pytest.raises(ValueError, match="no screen states"):
        stationary_distribution(P)

import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import (
    EXIT,
    START,
    absorption_probabilities,
    expected_steps_to_exit,
    transition_matrix,
)


def _edges(rows):
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


def test_one_step_chain_takes_exactly_one_step():
    # A -> EXIT 확률 1. 해석적 정답 1.
    P = transition_matrix(_edges([("A", EXIT, 1)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert got["A"] == pytest.approx(1.0)


def test_two_step_chain_takes_exactly_two_steps():
    # A -> B -> EXIT, 모두 확률 1. 해석적 정답 A=2, B=1.
    P = transition_matrix(_edges([("A", "B", 1), ("B", EXIT, 1)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert got["A"] == pytest.approx(2.0)
    assert got["B"] == pytest.approx(1.0)


def test_geometric_chain_matches_the_closed_form():
    # A 에서 확률 0.25 로 EXIT, 0.75 로 자기 자신. 기대 걸음 = 1/0.25 = 4.
    P = transition_matrix(_edges([("A", EXIT, 1), ("A", "A", 3)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert got["A"] == pytest.approx(4.0)


def test_expected_steps_are_always_positive():
    P = transition_matrix(
        _edges([("A", "B", 3), ("B", "C", 2), ("C", EXIT, 1), ("C", "A", 1)])
    )
    assert (expected_steps_to_exit(P)["expected_steps"] > 0).all()


def test_expected_steps_omits_start_and_exit():
    P = transition_matrix(_edges([(START, "A", 1), ("A", EXIT, 1)]))
    assert set(expected_steps_to_exit(P)["state"]) == {"A"}


def test_a_state_that_can_never_reach_exit_is_reported_as_infinite():
    # A<->B 만 오가고 EXIT 로 가는 길이 없다. 조용히 큰 수를 내면 안 된다.
    P = transition_matrix(_edges([("A", "B", 1), ("B", "A", 1), ("C", EXIT, 1)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert np.isinf(got["A"])
    assert np.isinf(got["B"])
    assert got["C"] == pytest.approx(1.0)


def test_a_state_that_might_fall_into_a_dead_end_is_also_infinite():
    """EXIT 로 가는 길이 있어도 기대값은 발산할 수 있다.

    A 는 절반 확률로 EXIT, 절반 확률로 D 로 간다. D 는 자기 루프라 영영 못 나온다.
    "EXIT 도달 가능하니 유한"으로 처리하면 A 에 그럴듯한 유한값(여기선 2.0 근처)이
    나온다. 실제 기대 걸음 수는 무한이다 — 절반은 영영 안 끝난다.
    """
    P = transition_matrix(_edges([("A", EXIT, 1), ("A", "D", 1), ("D", "D", 1)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert np.isinf(got["A"])
    assert np.isinf(got["D"])


def test_a_state_upstream_of_a_dead_end_is_infinite_too():
    # Z -> A -> (EXIT | D), D 는 막다른 곳. 오염은 상류로 전파된다.
    P = transition_matrix(
        _edges([("Z", "A", 1), ("A", EXIT, 1), ("A", "D", 1), ("D", "D", 1)])
    )
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert np.isinf(got["Z"])


def test_absorption_probabilities_sum_to_one_per_state():
    P = transition_matrix(
        _edges([("A", "GOAL", 1), ("A", EXIT, 3), ("GOAL", "GOAL", 1)])
    )
    got = absorption_probabilities(P, absorbing=("GOAL", EXIT))
    rows = got.set_index("state")
    assert rows.loc["A", ["GOAL", EXIT]].sum() == pytest.approx(1.0)


def test_absorption_probability_matches_hand_calculation():
    # A 에서 1/4 확률로 GOAL, 3/4 로 EXIT. 둘 다 흡수.
    P = transition_matrix(
        _edges([("A", "GOAL", 1), ("A", EXIT, 3), ("GOAL", "GOAL", 1)])
    )
    got = absorption_probabilities(P, absorbing=("GOAL", EXIT)).set_index("state")
    assert got.loc["A", "GOAL"] == pytest.approx(0.25)
    assert got.loc["A", EXIT] == pytest.approx(0.75)


def test_absorption_defaults_to_exit_only():
    P = transition_matrix(_edges([("A", "B", 1), ("B", EXIT, 1)]))
    got = absorption_probabilities(P)
    assert list(got.columns) == ["state", EXIT]
    assert got.set_index("state").loc["A", EXIT] == pytest.approx(1.0)


def test_absorption_rejects_a_state_that_is_not_in_the_chain():
    P = transition_matrix(_edges([("A", EXIT, 1)]))
    with pytest.raises(KeyError, match="NOPE"):
        absorption_probabilities(P, absorbing=("NOPE",))

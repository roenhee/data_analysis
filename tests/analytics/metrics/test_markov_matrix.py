import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import EXIT, START, TransitionMatrix, transition_matrix


def _edges(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


def test_rows_sum_to_one():
    P = transition_matrix(_edges([("A", "B", 3), ("A", "C", 1), ("B", "C", 2)]))
    assert np.allclose(P.matrix.sum(axis=1), 1.0)


def test_probabilities_are_counts_over_the_row_total():
    P = transition_matrix(_edges([("A", "B", 3), ("A", "C", 1)]))
    assert P.probability("A", "B") == pytest.approx(0.75)
    assert P.probability("A", "C") == pytest.approx(0.25)


def test_states_are_sorted_with_start_first_and_exit_last():
    P = transition_matrix(_edges([(START, "B", 1), ("B", EXIT, 1), ("B", "A", 1)]))
    assert P.states == [START, "A", "B", EXIT]


def test_exit_is_absorbing():
    P = transition_matrix(_edges([("A", EXIT, 1)]))
    assert P.probability(EXIT, EXIT) == pytest.approx(1.0)


def test_a_state_with_no_outgoing_edges_gets_a_self_loop():
    # 행 합이 1이 아니면 뒤의 모든 계산이 조용히 틀린다.
    P = transition_matrix(_edges([("A", "B", 1)]))
    assert P.probability("B", "B") == pytest.approx(1.0)
    assert np.allclose(P.matrix.sum(axis=1), 1.0)


def test_duplicate_edges_are_summed():
    P = transition_matrix(_edges([("A", "B", 1), ("A", "B", 3)]))
    assert P.count("A", "B") == 4


def test_zero_count_edges_do_not_create_states():
    P = transition_matrix(_edges([("A", "B", 1), ("C", "D", 0)]))
    assert "C" not in P.states


def test_empty_frame_is_rejected_rather_than_returning_an_empty_matrix():
    with pytest.raises(ValueError, match="no transitions"):
        transition_matrix(_edges([]))


def test_a_frame_whose_counts_are_all_zero_is_also_rejected():
    with pytest.raises(ValueError, match="no transitions"):
        transition_matrix(_edges([("A", "B", 0)]))


def test_unknown_state_lookup_raises():
    P = transition_matrix(_edges([("A", "B", 1)]))
    with pytest.raises(KeyError, match="Z"):
        P.probability("Z", "A")


def test_matrix_is_a_plain_numpy_array_of_floats():
    P = transition_matrix(_edges([("A", "B", 1)]))
    assert isinstance(P.matrix, np.ndarray)
    assert P.matrix.dtype == np.float64

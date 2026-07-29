import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import pointwise_mutual_information, transition_matrix


def _edges(rows):
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


def test_independent_transitions_have_zero_pmi():
    # 2x2 곱 구조: 관측이 독립 예측과 같으면 PMI = 0.
    P = transition_matrix(
        _edges([("A", "X", 1), ("A", "Y", 1), ("B", "X", 1), ("B", "Y", 1)])
    )
    got = pointwise_mutual_information(P)
    assert np.allclose(got["pmi"], 0.0, atol=1e-12)


def test_over_represented_transition_has_positive_pmi():
    P = transition_matrix(
        _edges([("A", "X", 9), ("A", "Y", 1), ("B", "X", 1), ("B", "Y", 9)])
    )
    got = pointwise_mutual_information(P).set_index(["from_state", "to_state"])["pmi"]
    assert got[("A", "X")] > 0
    assert got[("A", "Y")] < 0


def test_pmi_only_reports_observed_transitions():
    P = transition_matrix(_edges([("A", "X", 1), ("B", "Y", 1)]))
    got = pointwise_mutual_information(P)
    assert len(got) == 2


def test_pmi_carries_the_count_so_thin_cells_can_be_filtered():
    P = transition_matrix(_edges([("A", "X", 7)]))
    assert int(pointwise_mutual_information(P).iloc[0]["cnt"]) == 7


def test_pmi_is_symmetric_in_the_information_sense():
    # PMI(a,b) 는 log p(a,b)/(p(a)p(b)) 이므로 카운트 행렬을 전치하면 값이 보존된다.
    rows = [("A", "X", 9), ("A", "Y", 1), ("B", "X", 1), ("B", "Y", 9)]
    forward = pointwise_mutual_information(transition_matrix(_edges(rows)))
    flipped = pointwise_mutual_information(
        transition_matrix(_edges([(t, f, c) for f, t, c in rows]))
    )
    a = forward.set_index(["from_state", "to_state"])["pmi"][("A", "X")]
    b = flipped.set_index(["from_state", "to_state"])["pmi"][("X", "A")]
    assert a == pytest.approx(b)


def test_a_frequent_transition_between_common_states_can_have_low_pmi():
    """PMI 의 존재 이유. 빈도 1위가 PMI 1위가 아니다.

    A->X 는 카운트가 가장 크지만 A 도 X 도 흔해서 독립 예측과 큰 차이가 없다.
    B->Y 는 카운트가 작아도 그 쌍이 서로를 강하게 예측한다.
    """
    P = transition_matrix(
        _edges([("A", "X", 100), ("A", "Y", 1), ("B", "X", 1), ("B", "Y", 20)])
    )
    got = pointwise_mutual_information(P).set_index(["from_state", "to_state"])
    # A->X 는 카운트 100 이지만 PMI +0.18, B->Y 는 카운트 20 에 PMI +1.71.
    assert got["cnt"][("A", "X")] > got["cnt"][("B", "Y")]
    assert got["pmi"][("B", "Y")] > got["pmi"][("A", "X")]

import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import (
    EXIT,
    START,
    determinism,
    exit_probabilities,
    p_exit_within,
    pagerank,
    stationary_distribution,
    transition_matrix,
)


def _edges(rows):
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


def test_a_deterministic_screen_has_zero_entropy():
    # A -> B 확률 1. entropy 0, hhi 1, top_p 1, effective_choices 1.
    P = transition_matrix(_edges([("A", "B", 5), ("B", EXIT, 5)]))
    got = determinism(P).set_index("state").loc["A"]
    assert got["entropy"] == pytest.approx(0.0)
    assert got["hhi"] == pytest.approx(1.0)
    assert got["top_p"] == pytest.approx(1.0)
    assert got["effective_choices"] == pytest.approx(1.0)
    assert got["out_degree"] == 1
    assert got["top_to"] == "B"


def test_a_uniform_screen_has_maximum_entropy():
    # A -> B,C,D 각 1/3. entropy = log(3), effective_choices = 3.
    P = transition_matrix(_edges([("A", "B", 1), ("A", "C", 1), ("A", "D", 1)]))
    got = determinism(P).set_index("state").loc["A"]
    assert got["entropy"] == pytest.approx(np.log(3))
    assert got["effective_choices"] == pytest.approx(3.0)
    assert got["out_degree"] == 3


def test_effective_choices_is_exp_of_entropy():
    P = transition_matrix(
        _edges([("A", "B", 3), ("A", "C", 1), ("B", "C", 2), ("C", "A", 4),
                ("C", EXIT, 1)])
    )
    got = determinism(P)
    assert np.allclose(got["effective_choices"], np.exp(got["entropy"]))


def test_hhi_matches_the_hand_calculation():
    # A -> B 0.75, C 0.25 -> hhi = 0.5625 + 0.0625 = 0.625
    P = transition_matrix(_edges([("A", "B", 3), ("A", "C", 1)]))
    got = determinism(P).set_index("state").loc["A"]
    assert got["hhi"] == pytest.approx(0.625)
    assert got["top_p"] == pytest.approx(0.75)


def test_a_screen_with_no_observed_next_step_is_nan_not_certain():
    """`transition_matrix` 는 나가는 엣지가 없는 행에 자기 루프를 준다.

    그걸 그대로 재면 entropy 0 이 나와 "확실히 제자리에 머문다" 는 없는 사실이 된다.
    """
    P = transition_matrix(_edges([("A", "B", 5)]))
    got = determinism(P).set_index("state").loc["B"]
    assert pd.isna(got["entropy"])
    assert got["out_degree"] == 0
    # pandas 3.0 의 문자열 컬럼에서 `None` 은 NaN 으로 실린다 — 뜻은 "없음" 이다.
    assert pd.isna(got["top_to"])


def test_p_exit_within_one_equals_the_direct_exit_probability():
    P = transition_matrix(_edges([("A", "B", 6), ("A", EXIT, 4), ("B", EXIT, 10)]))
    direct = exit_probabilities(P).set_index("state")["exit_prob"]
    within = p_exit_within(P, 1).set_index("state")["p_exit_within"]
    assert within["A"] == pytest.approx(direct["A"])
    assert within["A"] == pytest.approx(0.4)


def test_p_exit_within_k_is_monotonically_non_decreasing_in_k():
    P = transition_matrix(
        _edges([("A", "B", 8), ("A", EXIT, 2), ("B", "A", 7), ("B", EXIT, 3)])
    )
    series = [p_exit_within(P, k).set_index("state")["p_exit_within"]["A"]
              for k in range(1, 8)]
    assert all(b >= a for a, b in zip(series, series[1:]))


def test_p_exit_within_a_large_k_approaches_one_when_exit_is_reachable():
    P = transition_matrix(
        _edges([("A", "B", 8), ("A", EXIT, 2), ("B", "A", 7), ("B", EXIT, 3)])
    )
    got = p_exit_within(P, 200).set_index("state")["p_exit_within"]
    assert got["A"] == pytest.approx(1.0)


def test_p_exit_within_refuses_a_chain_where_exit_is_not_absorbing():
    """EXIT 가 흡수가 아니면 `P^k` 의 EXIT 열은 "k 걸음 안에" 가 아니라 "정확히 k 걸음
    뒤에 EXIT 에 있다" 가 된다 — 나갔다 다시 들어온 경우를 빼먹는다.
    """
    P = transition_matrix(_edges([("A", EXIT, 5), (EXIT, "A", 1)]))
    with pytest.raises(ValueError, match="absorbing"):
        p_exit_within(P, 3)


def test_pagerank_sums_to_one():
    P = transition_matrix(
        _edges([("A", "B", 3), ("A", "C", 1), ("B", "C", 2), ("C", "A", 4)])
    )
    assert pagerank(P)["pagerank"].sum() == pytest.approx(1.0)


def test_pagerank_ranks_a_hub_above_a_leaf():
    P = transition_matrix(
        _edges([(START, "A", 10), ("A", "H", 8), ("A", "L", 2), ("B", "H", 5),
                ("C", "H", 3), ("H", EXIT, 10), ("L", EXIT, 2)])
    )
    got = pagerank(P).set_index("state")["pagerank"]
    assert got["H"] > got["L"]


def test_pagerank_differs_from_stationary_on_an_absorbing_chain():
    """노트북이 pi_cond 와 pi_pr 을 대조한 이유 — 둘은 다른 중심성이다.

    A -> B -> B 는 화면 부분체인 안에서 B 가 흡수다. 정상분포는 [0, 1] 로 "결국 전부 B"
    라고 답하고, 감쇠 랜덤서퍼는 텔레포트 몫이 있어 [0.075, 0.925] 다.
    """
    P = transition_matrix(_edges([("A", "B", 5), ("B", "B", 5)]))
    pi = stationary_distribution(P).set_index("state")["pi"]
    pr = pagerank(P, damping=0.85).set_index("state")["pagerank"]
    assert pi["A"] == pytest.approx(0.0)
    assert pr["A"] == pytest.approx(0.075)
    assert pr["B"] == pytest.approx(0.925)


def test_pagerank_needs_at_least_one_screen_state():
    P = transition_matrix(_edges([(START, EXIT, 1)]))
    with pytest.raises(ValueError, match="no screen states"):
        pagerank(P)

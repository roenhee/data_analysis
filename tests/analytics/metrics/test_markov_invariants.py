"""무작위 체인에 대한 속성 기반 불변식 검증.

마르코프 수식 버그는 예외를 안 던지고 그럴듯한 숫자를 낸다. 손계산 대조만으로는
좁으므로 무작위 입력에서 불변식이 깨지는지 본다.
"""
import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import (
    EXIT,
    absorption_probabilities,
    expected_steps_to_exit,
    pointwise_mutual_information,
    stationary_distribution,
    transition_matrix,
)

SEEDS = list(range(25))


def _random_chain(seed: int) -> pd.DataFrame:
    """모든 화면에서 EXIT 가 도달 가능한 무작위 체인."""
    rng = np.random.default_rng(seed)
    n = int(rng.integers(2, 7))
    screens = [f"S{i}" for i in range(n)]
    rows = []
    for s in screens:
        for t in screens:
            if rng.random() < 0.5:
                rows.append((s, t, int(rng.integers(1, 100))))
        rows.append((s, EXIT, int(rng.integers(1, 100))))  # 항상 이탈 경로가 있다
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_rows_always_sum_to_one(seed):
    P = transition_matrix(_random_chain(seed))
    assert np.allclose(P.matrix.sum(axis=1), 1.0)


@pytest.mark.parametrize("seed", SEEDS)
def test_stationary_always_sums_to_one_and_is_non_negative(seed):
    pi = stationary_distribution(transition_matrix(_random_chain(seed)))["pi"]
    assert pi.sum() == pytest.approx(1.0)
    assert (pi >= -1e-9).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_expected_steps_are_finite_and_at_least_one(seed):
    # 모든 화면에 EXIT 경로가 있으므로 유한해야 한다.
    steps = expected_steps_to_exit(transition_matrix(_random_chain(seed)))
    assert np.all(np.isfinite(steps["expected_steps"]))
    assert (steps["expected_steps"] >= 1.0 - 1e-9).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_absorption_probabilities_sum_to_one(seed):
    got = absorption_probabilities(transition_matrix(_random_chain(seed)))
    assert np.allclose(got[EXIT], 1.0)


@pytest.mark.parametrize("seed", SEEDS)
def test_pmi_is_finite_for_every_observed_transition(seed):
    got = pointwise_mutual_information(transition_matrix(_random_chain(seed)))
    assert np.all(np.isfinite(got["pmi"]))

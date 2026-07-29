"""빌드된 큐브가 있으면 실데이터로 지표를 돌려본다. 없으면 skip.

손으로 만든 체인은 실제 state 이름·커버리지·롤업 행 구조를 재현하지 못한다.
1단계에서 잡힌 결함들(dur_sum 이 100% 0, 롤업 행 중복 합산)의 회귀 그물이기도 하다.
"""
import glob

import numpy as np
import pandas as pd
import pytest

from analytics.metrics.descriptive import SESSION_AXES, engagement, screen_dwell, uv_pv
from analytics.metrics.frame import full_combination_rows, rollup_rows
from analytics.metrics.markov import (
    EXIT,
    START,
    exit_probabilities,
    expected_steps_to_exit,
    pointwise_mutual_information,
    stationary_distribution,
    transition_matrix,
)

def _newest_with_columns(pattern: str, required: set[str]) -> list[str]:
    """스키마가 맞는 파일만, 최신 순으로.

    캐시에는 옛 캐시 키로 만들어진 큐브가 남아 있을 수 있다(`dur_n` 이 생기기 전 것 등).
    아무 파일이나 집으면 실데이터 테스트가 스키마 불일치로 죽는데, 그건 지표의 결함이
    아니라 캐시의 잔재다. 현재 스키마를 가진 것만 고른다.
    """
    import os

    import pyarrow.parquet as pq

    out = []
    for path in glob.glob(pattern):
        try:
            names = set(pq.ParquetFile(path).schema.names)
        except Exception:
            continue
        if required <= names:
            out.append(path)
    return sorted(out, key=os.path.getmtime)


TRANSITION = _newest_with_columns(
    "cache/cubes/transition/*/date=*.parquet",
    {"from_state", "to_state", "cnt", "dur_sum", "dur_n"},
)
SESSION = _newest_with_columns(
    "cache/cubes/session/*/date=*.parquet",
    {"sessions", "uv", "pv", "events", "duration_sum"},
)

needs_transition = pytest.mark.skipif(
    not TRANSITION, reason="빌드된 전이 큐브가 없다 — scripts/build_cubes.py 를 먼저 돌려라"
)
needs_session = pytest.mark.skipif(
    not SESSION, reason="빌드된 세션 큐브가 없다 — scripts/build_cubes.py 를 먼저 돌려라"
)


@pytest.fixture(scope="module")
def edges() -> pd.DataFrame:
    df = pd.read_parquet(TRANSITION[-1])
    return df.groupby(["from_state", "to_state"], as_index=False)[
        ["cnt", "dur_sum", "dur_n"]
    ].sum()


@pytest.fixture(scope="module")
def sessions() -> pd.DataFrame:
    return pd.read_parquet(SESSION[-1])


# --- 마르코프 -----------------------------------------------------------------

@needs_transition
def test_the_chain_builds_and_rows_sum_to_one(edges):
    P = transition_matrix(edges)
    assert np.allclose(P.matrix.sum(axis=1), 1.0)


@needs_transition
def test_start_and_exit_are_present(edges):
    P = transition_matrix(edges)
    assert START in P.states
    assert EXIT in P.states


@needs_transition
def test_stationary_sums_to_one_on_real_data(edges):
    pi = stationary_distribution(transition_matrix(edges))["pi"]
    assert pi.sum() == pytest.approx(1.0)


@needs_transition
def test_exit_probabilities_are_between_zero_and_one(edges):
    p = exit_probabilities(transition_matrix(edges))["exit_prob"]
    assert (p >= 0).all() and (p <= 1.0 + 1e-9).all()


@needs_transition
def test_expected_steps_are_positive_and_plausible(edges):
    steps = expected_steps_to_exit(transition_matrix(edges))
    finite = steps[np.isfinite(steps["expected_steps"])]["expected_steps"]
    assert len(finite) > 0, "모든 화면이 무한대다 — 흡수 구조를 의심하라"
    assert (finite > 0).all()
    # 화면 전이가 한 세션에 수천 번 일어나지는 않는다. 크게 벗어나면 구조를 의심한다.
    assert finite.max() < 1000


@needs_transition
def test_pmi_is_finite_on_real_data(edges):
    assert np.all(np.isfinite(pointwise_mutual_information(transition_matrix(edges))["pmi"]))


# --- 체류 ---------------------------------------------------------------------

@needs_transition
def test_dwell_coverage_is_between_zero_and_one(edges):
    cov = screen_dwell(edges)["coverage"].dropna()
    assert (cov >= 0).all() and (cov <= 1.0 + 1e-9).all()


@needs_transition
def test_dwell_is_not_uniformly_zero(edges):
    # 1단계에서 dur_sum 이 100% 0 이던 결함의 회귀 그물.
    assert screen_dwell(edges)["measured_visits"].sum() > 0


@needs_transition
def test_dwell_per_visit_is_in_a_human_range(edges):
    # 실측 화면 평균은 7~65초였다. 1000배 틀리면(ms 를 초로 읽으면) 여기서 걸린다.
    seconds = screen_dwell(edges)["seconds_per_visit"].dropna()
    assert len(seconds) > 0
    assert seconds.max() < 3600, "화면 평균 체류가 1시간을 넘는다 — 단위를 의심하라"


# --- 기술통계 -----------------------------------------------------------------

@needs_session
def test_the_filtered_sum_matches_the_grand_total_row(sessions):
    full = full_combination_rows(sessions, SESSION_AXES)
    grand = rollup_rows(sessions, SESSION_AXES, folded=SESSION_AXES)
    assert len(grand) == 1
    assert int(full["sessions"].sum()) == int(grand["sessions"].iloc[0])


@needs_session
def test_uv_pv_returns_one_row_for_the_grand_total(sessions):
    got = uv_pv(sessions, folded=SESSION_AXES)
    assert len(got) == 1
    assert got.iloc[0]["uv"] > 0
    assert got.iloc[0]["pv"] > 0


@needs_session
def test_engagement_ratios_are_plausible(sessions):
    got = engagement(sessions, folded=SESSION_AXES).iloc[0]
    assert got["sessions_per_user"] >= 1.0
    assert got["pv_per_session"] > 0
    assert 0 < got["seconds_per_session"] < 86400
    assert got["dwell_definition"] == "session_span_seconds"

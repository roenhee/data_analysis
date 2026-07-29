"""화면 전이 분석. `metrics/markov.py` 의 프리미티브를 화면 한 줄로 합친다."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.analyses.base import (
    AnalysisResult,
    CubeSet,
    analysis,
    envelope_for,
)
from analytics.metrics.coverage import dwell_coverage
from analytics.metrics.markov import (
    EXIT,
    absorption_probabilities,
    exit_probabilities,
    expected_steps_to_exit,
    stationary_distribution,
    transition_matrix,
)


def _thin_cell_warning(edges: pd.DataFrame) -> list[dict]:
    """관측이 **하나뿐인** 전이 셀을 경고한다.

    임계치를 고르지 않는다 — cnt 1 은 "증거가 최소" 라는 정의이고, 그 확률 추정은
    임계치와 무관하게 못 믿는다. 실측 엣지 셀의 cnt 중앙값은 9고 18.9% 가 1이다.
    막지 않고 알린다: 얇은 셀도 합쳐 놓으면 전체 지표에는 기여한다.
    """
    used = edges[edges["cnt"] > 0]
    singles = int((used["cnt"] == 1).sum())
    if not singles:
        return []
    return [{
        "check_name": "thin_transition_cells",
        "single_observation_edges": singles,
        "share": float(singles / len(used)),
        "median_cnt": float(used["cnt"].median()),
    }]


@analysis("screen_flow")
def screen_flow(cubes: CubeSet, **_) -> AnalysisResult:
    """화면별 이탈확률·정상분포·EXIT 까지의 기대 걸음 수.

    `headline` 은 **방문 가중**이다. 화면끼리 단순 평균하면 방문이 거의 없는 화면이
    흔한 화면과 같은 무게를 갖고, 세그먼트마다 등장하는 화면 집합이 달라서 비교가
    깨진다. 방문 가중은 "무작위 화면 조회 하나"의 기대값이라 세그먼트 간 뜻이 같다.

    기대 걸음 수가 `inf` 면 그대로 낸다 — 빠져나올 수 없는 곳으로 갈 확률이 있으면
    기대값은 실제로 발산한다. 유한한 수로 반올림하면 그럴듯한 거짓말이 된다.

    PMI 는 넣지 않는다. 쌍(from, to) 단위 지표라 화면 한 줄에 담으려면 "어느 셀부터
    믿을 만한가" 하는 임계치를 발명해야 하고, 얇은 셀의 PMI 가 가장 크게 튄다.
    """
    edges = cubes.transition
    if edges is None:
        raise ValueError("screen_flow needs the transition cube; it is absent")
    P = transition_matrix(edges)

    frame = exit_probabilities(P).merge(
        stationary_distribution(P), on="state", how="left"
    ).merge(
        expected_steps_to_exit(P), on="state", how="left"
    ).merge(
        absorption_probabilities(P).rename(columns={EXIT: "p_reach_exit"}),
        on="state", how="left",
    )
    visits = {s: float(P.counts[i].sum()) for i, s in enumerate(P.states)}
    frame["visits"] = [visits[s] for s in frame["state"]]

    total_visits = float(frame["visits"].sum())
    if total_visits > 0:
        weights = frame["visits"] / total_visits
        mean_steps = float((frame["expected_steps"] * weights).sum())
        mean_exit = float((frame["exit_prob"] * weights).sum())
    else:
        mean_steps = mean_exit = float("nan")

    return AnalysisResult(
        frame=frame, headline={"mean_expected_steps": mean_steps,
                               "mean_exit_prob": mean_exit},
        compare_key="state",
        envelope=envelope_for(
            cubes, {"dwell": dwell_coverage(edges)}, _thin_cell_warning(edges)
        ),
        viz={"kind": "bar", "x": "state"},
    )

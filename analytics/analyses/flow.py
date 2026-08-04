"""화면 전이 분석. `metrics/markov.py` 의 프리미티브를 이름 붙인 분석으로 묶는다.

대부분은 화면 한 줄짜리 프레임이지만 `screen_pair_affinity` 는 **쌍(from, to) 한 줄**이다 —
같은 프레임에 담을 수 없어서 분석이 따로 있다.
"""
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
    determinism,
    exit_probabilities,
    expected_steps_to_exit,
    p_exit_within,
    pagerank,
    pointwise_mutual_information,
    stationary_distribution,
    transition_matrix,
)
from analytics.metrics.services import services_of


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
def screen_flow(cubes: CubeSet, exit_within: tuple[int, ...] = (),
                damping: float = 0.85, **_) -> AnalysisResult:
    """화면별 이탈확률·정상분포·기대 걸음 수·결정성·PageRank.

    `headline` 은 **방문 가중**이다. 화면끼리 단순 평균하면 방문이 거의 없는 화면이
    흔한 화면과 같은 무게를 갖고, 세그먼트마다 등장하는 화면 집합이 달라서 비교가
    깨진다. 방문 가중은 "무작위 화면 조회 하나"의 기대값이라 세그먼트 간 뜻이 같다.

    기대 걸음 수가 `inf` 면 그대로 낸다 — 빠져나올 수 없는 곳으로 갈 확률이 있으면
    기대값은 실제로 발산한다. 유한한 수로 반올림하면 그럴듯한 거짓말이 된다.

    `exit_within` 을 주면 그 지평마다 "k 걸음 안에 이탈" 열을 붙인다. **기본값은
    없다** — 어느 지평이 궁금한지는 부르는 쪽이 안다. 기대 걸음 수(평균)와 달리
    분포의 한 점이라, `inf` 가 섞인 체인에서도 읽을 수 있는 값이다.

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
    ).merge(
        determinism(P), on="state", how="left"
    ).merge(
        pagerank(P, damping=damping), on="state", how="left"
    )
    for k in exit_within:
        horizon = p_exit_within(P, k).set_index("state")["p_exit_within"]
        frame[f"p_exit_within_{k}"] = [horizon[s] for s in frame["state"]]

    visits = {s: float(P.counts[i].sum()) for i, s in enumerate(P.states)}
    frame["visits"] = [visits[s] for s in frame["state"]]

    total_visits = float(frame["visits"].sum())
    headline = {}
    if total_visits > 0:
        weights = frame["visits"] / total_visits
        headline["mean_expected_steps"] = float(
            (frame["expected_steps"] * weights).sum()
        )
        headline["mean_exit_prob"] = float((frame["exit_prob"] * weights).sum())
        # 이탈 lift: 각 화면 이탈률이 방문 가중 평균의 몇 배인가(노트북 lift_exit).
        baseline = headline["mean_exit_prob"]
        frame["exit_baseline"] = baseline
        frame["exit_lift"] = (frame["exit_prob"] / baseline
                              if baseline > 0 else float("nan"))
        for k in exit_within:
            headline[f"mean_p_exit_within_{k}"] = float(
                (frame[f"p_exit_within_{k}"] * weights).sum()
            )
    else:
        headline["mean_expected_steps"] = headline["mean_exit_prob"] = float("nan")
        frame["exit_baseline"] = float("nan")
        frame["exit_lift"] = float("nan")

    return AnalysisResult(
        frame=frame, headline=headline,
        compare_key="state",
        envelope=envelope_for(
            cubes, {"dwell": dwell_coverage(edges)}, _thin_cell_warning(edges)
        ),
        viz={"kind": "bar", "x": "state"},
    )


@analysis("reachability")
def reachability(cubes: CubeSet, source: str, target: str, max_k: int = 10,
                 **_) -> AnalysisResult:
    """`source` 에서 `target` 에 **k 걸음 안에** 닿을 확률의 곡선.

    노트북의 "홈 → 뉴스뷰 도달 속도" 가 이 형태였다. 기대 걸음 수 하나로는 "빠르게
    닿는 소수 + 안 닿는 다수" 와 "다들 중간에 닿는다" 가 구분되지 않는다.

    **목표를 흡수 상태로 바꾼 뒤 거듭제곱한다.** 안 그러면 `P^k` 의 목표 열은 "정확히
    k 걸음 뒤 그 화면에 있다" 가 되어, 닿았다가 떠난 경우가 빠지고 곡선이 내려간다 —
    "3걸음 안에 닿을 확률이 2걸음 안보다 낮다" 는 있을 수 없는 답이 나온다.

    `max_k` 기본값 10 은 화면 수의 표시 지평이다. 실측 기대 걸음 수가 11.5~13.2 이라
    한 세션 대부분을 덮는다. 곡선 전체가 프레임에 있으므로 이 값이 정보를 숨기지는
    않는다 — `headline` 이 어느 지평의 값인지만 정한다.
    """
    edges = cubes.transition
    if edges is None:
        raise ValueError("reachability needs the transition cube; it is absent")
    if max_k < 1:
        raise ValueError(f"max_k must be at least 1, got {max_k}")
    if source == target:
        raise ValueError(
            f"source and target are both {source!r}; 'reaching' a screen you are "
            "already on is 1.0 at every k and says nothing"
        )
    P = transition_matrix(edges)
    for role, state in (("source", source), ("target", target)):
        if state not in P.states:
            raise KeyError(
                f"unknown {role} state: {state!r}; this chain has "
                f"{len(P.states)} states"
            )

    absorbed = P.matrix.copy()
    target_index = P.states.index(target)
    absorbed[target_index] = 0.0
    absorbed[target_index, target_index] = 1.0

    source_index = P.states.index(source)
    powered = np.eye(len(P.states))
    rows = []
    for k in range(1, max_k + 1):
        powered = powered @ absorbed
        rows.append({"source": source, "target": target, "k": k,
                     "p_hit_within": float(powered[source_index, target_index])})
    frame = pd.DataFrame(rows)

    return AnalysisResult(
        frame=frame,
        headline={f"p_hit_within_{max_k}": float(frame["p_hit_within"].iloc[-1])},
        compare_key="k",
        envelope=envelope_for(
            cubes, {"dwell": dwell_coverage(edges)}, _thin_cell_warning(edges)
        ),
        viz={"kind": "line", "x": "k"},
    )


@analysis("screen_pair_affinity")
def screen_pair_affinity(cubes: CubeSet, **_) -> AnalysisResult:
    """전이 쌍의 **결합 강도**(PMI). 빈도 순위와 다른 질문에 답한다.

    PMI 는 "흔한 화면이라 흔한" 전이를 걸러낸다 — 카운트 1위가 PMI 1위가 아닌 것이
    이 지표의 존재 이유다. `screen_flow` 에 넣을 수 없는 이유는 쌍 단위라 화면 한 줄에
    안 들어가기 때문이고, 넣으려면 "어느 셀부터 믿을 만한가" 하는 임계치를 발명해야
    한다. **임계치를 만들지 않고 `cnt` 를 함께 낸다** — 얇은 셀의 PMI 가 가장 크게 튀므로
    소비자가 그 열을 보고 거른다.

    `headline` 의 `mutual_information` 은 `Σ p(i,j)·PMI(i,j)` 로, 곧 상호정보량
    I(현재 화면; 다음 화면) 이다(nats). "현재 화면을 알면 다음 화면을 얼마나 아는가" 이고,
    쌍마다 값이 다른 PMI 와 달리 세그먼트끼리 견줄 수 있는 스칼라다. 0 이면 다음 화면이
    현재와 독립이고, 완전히 결정적이며 후보가 둘이면 log(2) 다.

    **`START`·`EXIT` 쌍을 빼지 않는다.** `screen_communities` 는 그 둘이 모든 화면과
    이어져 군집을 뭉개므로 뺐지만, 여기서는 `START→X` 가 "어느 화면이 세션을 특징적으로
    시작하는가", `X→EXIT` 가 "어느 화면이 특징적으로 끝내는가" 라는 실제 질문에 답한다.
    상호정보량도 그 둘을 포함한 전이 분포 전체에 대한 값이라야 뜻이 온전하다.

    커버리지는 비운다 — 카운트만 쓰므로 부분 측정 문제가 없다. 체류 커버리지를 실으면
    쓰지도 않은 측정값의 신뢰도를 말하는 셈이다.
    """
    edges = cubes.transition
    if edges is None:
        raise ValueError("screen_pair_affinity needs the transition cube; it is absent")
    P = transition_matrix(edges)
    frame = pointwise_mutual_information(P).sort_values(
        "pmi", ascending=False, ignore_index=True
    )
    total = float(frame["cnt"].sum())
    weights = frame["cnt"] / total if total > 0 else 0.0
    return AnalysisResult(
        frame=frame,
        headline={
            "mutual_information": float((frame["pmi"] * weights).sum())
            if total > 0 else float("nan"),
            "pairs": float(len(frame)),
        },
        # `compare_key` 는 없다 — 쌍 프레임에서 `from_state` 는 유일 키가 아니라
        # 행별 조인이 여러 `to_state` 를 한 행으로 뭉갠다.
        envelope=envelope_for(cubes, {}, _thin_cell_warning(edges)),
        viz={"kind": "heatmap", "x": "from_state"},
    )


@analysis("cross_service_flow")
def cross_service_flow(cubes: CubeSet, **_) -> AnalysisResult:
    """서비스 사이의 이동. **화면 간 전이의 절반이 여기 있다.**

    실측 15일에서 화면 간 전이 35.4억 건 중 49.68%가 서비스를 건너뛴다. 그게 이 앱의
    실제 사용 행태인데(세션 44.7%가 여러 서비스에 걸친다) 어느 분석도 보여주지 않았다 —
    `screen_flow` 는 화면 단위라 서비스가 안 보이고, `per_service` 는 이 전이를 **버린다.**

    `START`·`EXIT` 는 뺀다. 세션 경계는 서비스 간 이동이 아니고, 넣으면 분모가 세션
    수만큼 부푼다. `screen_pair_affinity` 가 둘을 넣는 것과 반대인데, 거기서는
    "어느 화면이 세션을 시작하는가" 가 답할 질문이었고 여기서는 아니다.

    `switch_entropy` 는 **건너뛰는 이동에 한정한** 목적지 분포의 엔트로피(nats)다.
    0 이면 모든 이동이 한 쌍으로만 가고, 크면 여러 방향으로 흩어진다. `cross_service_share`
    가 "얼마나 넘나드나" 이고 이쪽이 "어디로 넘나드나" 다.

    커버리지는 비운다 — 카운트만 쓴다.
    """
    edges = cubes.transition
    if edges is None:
        raise ValueError("cross_service_flow needs the transition cube; it is absent")
    frame = pd.DataFrame({
        "from_service": services_of(edges["from_state"]),
        "to_service": services_of(edges["to_state"]),
        "cnt": edges["cnt"],
    })
    frame = frame[frame["from_service"].notna() & frame["to_service"].notna()]
    if frame.empty or float(frame["cnt"].sum()) <= 0:
        raise ValueError(
            "no screen-to-screen transitions: every edge touches START or EXIT, so "
            "there is no service movement to report"
        )

    grouped = frame.groupby(["from_service", "to_service"], as_index=False)["cnt"].sum()
    origin = grouped.groupby("from_service")["cnt"].transform("sum")
    grouped["share_of_origin"] = grouped["cnt"] / origin
    grouped = grouped.sort_values("cnt", ascending=False, ignore_index=True)

    total = float(grouped["cnt"].sum())
    switches = grouped[grouped["from_service"] != grouped["to_service"]]
    switch_total = float(switches["cnt"].sum())
    if switch_total > 0:
        p = switches["cnt"].to_numpy(dtype=float) / switch_total
        entropy = float(-(p * np.log(p)).sum())
    else:
        # 건너뛰는 이동이 없다 = "없다" 이고 "모른다" 가 아니다. NaN 으로 내면 소비자가
        # 계측 실패와 구분할 수 없다.
        entropy = 0.0

    return AnalysisResult(
        frame=grouped,
        headline={
            "cross_service_share": switch_total / total,
            "switch_entropy": entropy,
        },
        envelope=envelope_for(cubes, {}, _thin_cell_warning(edges)),
        viz={"kind": "heatmap", "x": "from_service"},
    )

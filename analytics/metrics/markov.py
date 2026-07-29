"""마르코프 지표. 큐브 프레임만 받는 순수 함수다.

수식 버그는 예외를 던지지 않고 **그럴듯한 숫자**를 낸다. 그래서 이 모듈은 DB 를 모르고,
손으로 만든 2~3 상태 체인으로 해석적 정답과 대조할 수 있어야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

START = "START"
EXIT = "EXIT"


def _ordered_states(states: set[str]) -> list[str]:
    """START 먼저, EXIT 마지막, 나머지는 사전순. 행렬을 눈으로 읽을 수 있게 한다."""
    middle = sorted(s for s in states if s not in (START, EXIT))
    out = []
    if START in states:
        out.append(START)
    out.extend(middle)
    if EXIT in states:
        out.append(EXIT)
    return out


@dataclass(frozen=True)
class TransitionMatrix:
    """행 확률 행렬과 원본 카운트."""

    states: list[str]
    matrix: np.ndarray
    counts: np.ndarray

    def _index(self, state: str) -> int:
        try:
            return self.states.index(state)
        except ValueError:
            raise KeyError(f"unknown state: {state!r}") from None

    def probability(self, from_state: str, to_state: str) -> float:
        return float(self.matrix[self._index(from_state), self._index(to_state)])

    def count(self, from_state: str, to_state: str) -> float:
        return float(self.counts[self._index(from_state), self._index(to_state)])


def transition_matrix(edges: pd.DataFrame) -> TransitionMatrix:
    """`(from_state, to_state, cnt)` 프레임을 행 확률 행렬로.

    행 합은 반드시 1이다. 나가는 엣지가 없는 상태(EXIT 포함)는 자기 루프를 준다 —
    행 합이 1이 아니면 stationary·expected steps 가 전부 조용히 틀린다.
    """
    # 완전히 빈 프레임은 컬럼조차 없어서 `edges["cnt"]` 가 KeyError 를 낸다.
    # 큐브에서 읽은 빈 결과는 컬럼이 있고 행이 0이다. 둘 다 같은 뜻이므로 같이 처리한다.
    if edges.empty or "cnt" not in edges.columns:
        raise ValueError("no transitions: the frame is empty")
    used = edges[edges["cnt"] > 0]
    if used.empty:
        raise ValueError("no transitions: the frame has no rows with cnt > 0")

    grouped = used.groupby(["from_state", "to_state"], as_index=False)["cnt"].sum()
    states = _ordered_states(set(grouped["from_state"]) | set(grouped["to_state"]))
    index = {s: i for i, s in enumerate(states)}

    counts = np.zeros((len(states), len(states)), dtype=np.float64)
    for row in grouped.itertuples():
        counts[index[row.from_state], index[row.to_state]] = float(row.cnt)

    totals = counts.sum(axis=1)
    matrix = np.zeros_like(counts)
    for i, total in enumerate(totals):
        if total > 0:
            matrix[i] = counts[i] / total
        else:
            matrix[i, i] = 1.0  # 흡수: 나가는 곳이 없다
    return TransitionMatrix(states=states, matrix=matrix, counts=counts)


def _screen_states(P: TransitionMatrix) -> list[str]:
    return [s for s in P.states if s not in (START, EXIT)]


def exit_probabilities(P: TransitionMatrix) -> pd.DataFrame:
    """화면별 "다음 걸음이 이탈일 확률". START·EXIT 자신은 제외한다.

    이탈의 정의는 **"그 세션의 마지막 화면"** 이다 — 타임아웃도 명시적 종료 이벤트도
    아니다. 앱에서는 실측 88.6% 가 마지막 화면 뒤에 `AppExit` 를 갖지만, 웹에는 종료
    신호가 없어 "로그가 끊겼다" 이상을 말할 수 없다. `service_type` 으로 나눠 읽는다.
    """
    screens = _screen_states(P)
    if EXIT not in P.states:
        return pd.DataFrame({"state": screens, "exit_prob": [0.0] * len(screens)})
    return pd.DataFrame(
        {
            "state": screens,
            "exit_prob": [P.probability(s, EXIT) for s in screens],
        }
    )


def stationary_distribution(P: TransitionMatrix) -> pd.DataFrame:
    """화면 전용 부분체인의 정상분포 π (π = πP, Σπ = 1).

    **START·EXIT 를 뺀 뒤 행을 재정규화한다.** 전체 체인은 EXIT 가 흡수 상태라
    정상분포가 전부 EXIT 에 몰린 자명한 답("결국 모두 나간다")이 되어 쓸모가 없다.
    알고 싶은 것은 둘러보는 동안의 화면 비중이다.
    """
    screens = _screen_states(P)
    if not screens:
        raise ValueError("no screen states: the chain is only START/EXIT")
    idx = [P.states.index(s) for s in screens]
    sub = P.matrix[np.ix_(idx, idx)].copy()

    totals = sub.sum(axis=1, keepdims=True)
    for i in range(len(screens)):
        if totals[i, 0] <= 0:
            sub[i, i] = 1.0  # 화면 밖으로만 나가는 상태: 자기 루프로 흡수
            totals[i, 0] = 1.0
    sub = sub / totals

    # πP = π, Σπ = 1 을 선형계로 푼다. 고유벡터보다 수치적으로 안정적이다.
    n = len(screens)
    A = np.vstack([sub.T - np.eye(n), np.ones(n)])
    b = np.append(np.zeros(n), 1.0)
    pi, *_ = np.linalg.lstsq(A, b, rcond=None)
    return pd.DataFrame({"state": screens, "pi": pi})


def _closure(P: TransitionMatrix, seed: set[str]) -> set[str]:
    """`seed` 중 하나에라도 도달할 수 있는 상태 집합(자기 자신 포함)."""
    out = set(seed)
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(P.states):
            if s in out:
                continue
            for j, t in enumerate(P.states):
                if t in out and P.matrix[i, j] > 0:
                    out.add(s)
                    changed = True
                    break
    return out


def expected_steps_to_exit(P: TransitionMatrix) -> pd.DataFrame:
    """각 화면에서 EXIT 까지의 기대 걸음 수.

    **EXIT 에 확률 1로 닿지 못하면 `inf` 다.** 여기가 조용히 틀리기 쉬운 자리다:
    "EXIT 로 가는 길이 있으니 유한"이 **아니다.** 도중에 빠져나올 수 없는 곳으로 갈
    확률이 조금이라도 있으면 기대값은 발산한다. 그 경우까지 역행렬을 밀어붙이면
    "평균 3.7걸음이면 나간다" 같은 그럴듯한 거짓말이 나온다.

    그래서 두 단계로 거른다. ① EXIT 에 도달 **못** 하는 상태(`dead`)를 찾고,
    ② 거기 도달할 수 있는 상태까지 전부 오염(`tainted`)으로 본다. 남은 상태들은
    후속 상태가 전부 깨끗하거나 EXIT 이므로 `I - Q` 가 반드시 가역이다.
    """
    transient = [s for s in P.states if s not in (EXIT, START)]
    if not transient:
        return pd.DataFrame({"state": [], "expected_steps": []})

    reaches_exit = _closure(P, {EXIT}) if EXIT in P.states else set()
    dead = {s for s in P.states if s not in reaches_exit}
    tainted = _closure(P, dead) if dead else set()
    good = [s for s in transient if s not in tainted]

    steps = {s: float(np.inf) for s in transient}
    if good:
        idx = [P.states.index(s) for s in good]
        Q = P.matrix[np.ix_(idx, idx)]
        N = np.linalg.inv(np.eye(len(good)) - Q)
        for state, value in zip(good, N.sum(axis=1)):
            steps[state] = float(value)
    return pd.DataFrame(
        {"state": transient, "expected_steps": [steps[s] for s in transient]}
    )


def absorption_probabilities(
    P: TransitionMatrix, absorbing: tuple[str, ...] = (EXIT,)
) -> pd.DataFrame:
    """전이 상태에서 각 흡수 상태에 결국 닿을 확률. 행 합은 1이다.

    흡수 집합에 절대 닿지 못하는 상태가 있으면 `I - Q` 가 특이행렬이 된다. 그때는
    `NaN` 으로 표기한다 — 유사역행렬로 얼버무리면 합이 1이 아닌 확률이 조용히 나온다.
    """
    for state in absorbing:
        if state not in P.states:
            raise KeyError(f"unknown state: {state!r}")
    transient = [s for s in P.states if s not in absorbing and s != START]
    if not transient:
        return pd.DataFrame({"state": [], **{a: [] for a in absorbing}})

    t_idx = [P.states.index(s) for s in transient]
    Q = P.matrix[np.ix_(t_idx, t_idx)]
    try:
        N = np.linalg.inv(np.eye(len(transient)) - Q)
    except np.linalg.LinAlgError:
        N = None
    if N is None or not np.all(np.isfinite(N)):
        return pd.DataFrame(
            {"state": transient, **{a: [np.nan] * len(transient) for a in absorbing}}
        )

    a_idx = [P.states.index(a) for a in absorbing]
    B = N @ P.matrix[np.ix_(t_idx, a_idx)]
    out = {"state": transient}
    for k, name in enumerate(absorbing):
        out[name] = B[:, k]
    return pd.DataFrame(out)


def pointwise_mutual_information(P: TransitionMatrix) -> pd.DataFrame:
    """관측 전이가 독립 가정보다 얼마나 흔한가.

    `PMI(i,j) = log( p(i,j) / (p(i)·p(j)) )`. 양수면 그 쌍이 예상보다 자주 일어난다.
    빈도 순위와 달리 "흔한 화면이라 흔한" 전이를 걸러낸다 — 카운트 1위가 PMI 1위가
    아닌 것이 이 지표의 존재 이유다.

    `cnt` 를 함께 낸다. 얇은 셀의 PMI 는 크게 튀므로 소비자가 걸러야 한다.
    """
    total = P.counts.sum()
    if total <= 0:
        raise ValueError("no transitions")
    p_from = P.counts.sum(axis=1) / total
    p_to = P.counts.sum(axis=0) / total

    rows = []
    for i, f in enumerate(P.states):
        for j, t in enumerate(P.states):
            c = P.counts[i, j]
            if c <= 0:
                continue
            joint = c / total
            expected = p_from[i] * p_to[j]
            rows.append(
                {
                    "from_state": f,
                    "to_state": t,
                    "cnt": c,
                    "pmi": float(np.log(joint / expected)),
                }
            )
    return pd.DataFrame(rows)

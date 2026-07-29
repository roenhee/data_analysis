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

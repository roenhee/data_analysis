"""화면 군집. 이 층에서 유일하게 외부 의존(`networkx`)이 붙는 분석이다."""
from __future__ import annotations

import networkx as nx
import pandas as pd

from analytics.analyses.base import (
    AnalysisResult,
    CubeSet,
    analysis,
    envelope_for,
)
from analytics.metrics.coverage import dwell_coverage
from analytics.metrics.markov import EXIT, START

# Louvain 은 무작위 초기화가 있다. 시드가 발행물의 재현성을 결정하므로 상수로 박는다.
DEFAULT_SEED = 0


def _screen_graph(edges: pd.DataFrame) -> nx.Graph:
    """화면끼리의 무향 가중 그래프.

    **`START`·`EXIT` 를 뺀다.** 둘은 거의 모든 화면과 이어져 있어서 넣으면 전체가 한
    덩어리로 뭉개진다 — 군집이 2개인 그래프가 1개로 나온다.

    방향을 접는다. 군집은 "함께 오가는 화면들" 이고 A→B 와 B→A 는 같은 유대다.
    """
    used = edges[(edges["cnt"] > 0)
                 & ~edges["from_state"].isin((START, EXIT))
                 & ~edges["to_state"].isin((START, EXIT))]
    graph = nx.Graph()
    for row in used.itertuples():
        weight = float(row.cnt)
        if graph.has_edge(row.from_state, row.to_state):
            graph[row.from_state][row.to_state]["weight"] += weight
        else:
            graph.add_edge(row.from_state, row.to_state, weight=weight)
    return graph


@analysis("screen_communities")
def screen_communities(cubes: CubeSet, seed: int = DEFAULT_SEED,
                       resolution: float = 1.0, **_) -> AnalysisResult:
    """함께 오가는 화면 묶음(Louvain).

    **시드를 고정한다.** Louvain 은 무작위 초기화가 있어 고정하지 않으면 실행마다 군집이
    바뀌고, 그러면 같은 질문에 두 답이 발행된다.

    시드만으로는 부족해서 군집 **번호**도 못 박는다. Louvain 이 돌려주는 집합의 순서는
    그래프 노드 순서를 따르고, 그 노드 순서는 **엣지 행 순서**를 따른다 — 같은 군집인데
    큐브 행 순서만 바뀌어도 번호가 뒤집힌다(확인: 두 클러스터의 행 순서를 맞바꾸면
    원시 순서가 `[[A,B,C],[X,Y,Z]]` 에서 `[[X,Y,Z],[A,B,C]]` 로 뒤집혔다). 읽는 날짜
    범위나 parquet 파일 순서만 달라져도 생기는 일이라, 무게 내림차순·같으면 첫 화면
    이름순으로 0번부터 다시 매긴다. 그래서 0번은 항상 가장 큰 군집이다.
    """
    edges = cubes.transition
    if edges is None:
        raise ValueError("screen_communities needs the transition cube; it is absent")
    graph = _screen_graph(edges)
    if graph.number_of_edges() == 0:
        raise ValueError(
            "no screen-to-screen edges after dropping START and EXIT; there is "
            "nothing to cluster — every session here is a single screen"
        )

    found = nx.community.louvain_communities(
        graph, weight="weight", seed=seed, resolution=resolution
    )
    weight_of = dict(graph.degree(weight="weight"))
    ordered = sorted(
        found,
        key=lambda group: (-sum(weight_of[s] for s in group), min(group)),
    )

    frame = pd.DataFrame([
        {"state": state, "community": index, "degree": float(weight_of[state]),
         "community_size": len(group)}
        for index, group in enumerate(ordered)
        for state in sorted(group)
    ]).sort_values("state", ignore_index=True)

    return AnalysisResult(
        frame=frame,
        headline={
            "communities": float(len(ordered)),
            "modularity": float(
                nx.community.modularity(graph, ordered, weight="weight")
            ),
        },
        compare_key="state",
        envelope=envelope_for(cubes, {"dwell": dwell_coverage(edges)}),
        viz={"kind": "graph", "x": "state"},
    )

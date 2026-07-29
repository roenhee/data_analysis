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
    # **먼저 쌍으로 묶고 정렬한다.** 두 가지를 동시에 고친다.
    #
    # 속도: 세그먼트 축이 붙은 큐브는 같은 쌍이 수만 행으로 흩어져 있다(실측 15일치
    # 화면 엣지 2,538,274 행 대 화면 쌍 221개). 행마다 그래프를 건드리면 15개 노드짜리
    # 군집에 8.8초가 걸렸다. 묶으면 0.48초다.
    #
    # 재현성: 노드 삽입 순서가 Louvain 의 답을 바꾼다. **시드를 고정해도 그렇다.**
    # 실측에서 행 단위로 조립한 그래프와 묶어서 조립한 그래프는 노드·엣지·가중치가
    # 완전히 같은데(가중치 다른 엣지 0개) 군집이 4개(Q=0.395878) 대 3개(Q=0.394087)로
    # 갈렸다. 정렬해서 넣으면 큐브 행 순서와 무관하게 같은 그래프가 나온다.
    pairs = used.groupby(["from_state", "to_state"], as_index=False)["cnt"].sum(
    ).sort_values(["from_state", "to_state"], ignore_index=True)

    graph = nx.Graph()
    for row in pairs.itertuples():
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

    시드만으로는 부족하다. 노드 삽입 순서가 Louvain 의 답을 바꾸므로 그래프 조립을
    `_screen_graph` 에서 정렬로 못 박고, 군집 **번호**도 무게 내림차순(같으면 첫 화면
    이름순)으로 다시 매긴다. 그래서 0번은 항상 가장 큰 군집이다.

    **군집 수를 강한 사실로 읽지 말 것.** 실측 15일치는 화면이 15개뿐이고 modularity
    0.394 인데, 노드 순서만 다른 같은 그래프에서 4개(Q=0.395878) 와 3개(Q=0.394087) 가
    나왔다. 두 분할의 품질 차이가 0.002 라 사실상 무승부다 — 어느 화면들이 함께 묶이는
    경향인지는 읽을 수 있어도 "군집이 정확히 N개" 는 이 데이터가 답할 수 있는 질문이
    아니다.
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

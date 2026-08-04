"""viz.kind → 차트 데이터 준비. 순수 — st.* 호출 없음.

app.py 가 반환값을 st.bar_chart / st.line_chart / st.dataframe 에 넘긴다. graph 는 이
함수들을 거치지 않는다 — app.py 가 viz.kind == "graph" 를 먼저 갈라 graph_dot() 이 만든
DOT 문자열을 st.graphviz_chart 로 그린다. chart_kind 는 나머지(bar/line/heatmap)만
분류하고, 그 밖의(정말 지원하지 않는) kind 만 "table" 로 떨어뜨린다.
"""
from __future__ import annotations

import pandas as pd

_SUPPORTED = {"bar", "line", "heatmap"}

# 색맹 친화 팔레트(Tableau 10). community 번호를 색으로.
_PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1",
            "#76b7b2", "#edc948", "#ff9da7", "#9c755f", "#bab0ac"]


def chart_kind(viz: dict) -> str:
    """그릴 차트 종류. 지원 안 하는 kind(graph 는 app.py 가 따로 그린다)는 표로."""
    kind = viz.get("kind", "table")
    return kind if kind in _SUPPORTED else "table"


def bar_data(frame: pd.DataFrame, x: str, y: str, top: int) -> pd.Series:
    """x 를 인덱스로, y 를 값으로 하는 상위 top 시리즈."""
    return frame.head(max(0, top)).set_index(x)[y]


def line_data(frame: pd.DataFrame, x: str) -> pd.DataFrame:
    """x 를 인덱스로, 수치 열만 선으로. 문자열/혼합 열은 뺀다(차트가 못 그린다)."""
    return frame.set_index(x).select_dtypes(include="number")


def heatmap_pivot(frame: pd.DataFrame, from_col: str, to_col: str,
                  value: str) -> pd.DataFrame:
    """(from, to) 격자. 값은 value 열."""
    return frame.pivot_table(index=from_col, columns=to_col, values=value,
                             aggfunc="sum", fill_value=0)


def graph_dot(frame: pd.DataFrame, viz: dict, label_of=None) -> str:
    """군집 그래프를 Graphviz DOT 문자열로. 노드 색 = community, 엣지 굵기 = 가중치.

    `label_of(state) -> str` 로 노드 라벨을 한글화할 수 있다(없으면 state 그대로).
    노드 id 는 화면 이름 그대로 쓰되 따옴표로 감싼다(`/`·`_`·한글 안전).
    """
    node_col = viz.get("x", "state")
    community = dict(zip(frame[node_col], frame["community"]))
    label = label_of or (lambda s: s)
    lines = ["graph G {",
             '  node [style=filled, fontname="sans-serif", shape=ellipse];']
    for node, comm in community.items():
        color = _PALETTE[int(comm) % len(_PALETTE)]
        safe = str(label(node)).replace('"', "'")
        lines.append(f'  "{node}" [fillcolor="{color}", label="{safe}"];')
    edges = viz.get("edges", [])
    wmax = max((w for _, _, w in edges), default=1.0) or 1.0
    for u, v, w in edges:
        pen = 1.0 + 4.0 * (float(w) / wmax)   # 1.0 ~ 5.0
        lines.append(f'  "{u}" -- "{v}" [penwidth={pen:.2f}];')
    lines.append("}")
    return "\n".join(lines)

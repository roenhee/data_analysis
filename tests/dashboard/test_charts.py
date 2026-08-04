import pandas as pd

from dashboard.charts import chart_kind, bar_data, line_data, heatmap_pivot, graph_dot


def test_chart_kind_reads_viz():
    assert chart_kind({"kind": "bar", "x": "state"}) == "bar"


def test_graph_falls_back_to_table_in_this_plan():
    """graph(networkx)는 3계획서. 지금은 표로."""
    assert chart_kind({"kind": "graph", "x": "state"}) == "table"


def test_missing_kind_is_table():
    assert chart_kind({}) == "table"


def test_bar_data_indexes_by_x_and_takes_top():
    frame = pd.DataFrame({"state": ["a", "b", "c"], "pagerank": [0.3, 0.5, 0.2]})
    series = bar_data(frame, x="state", y="pagerank", top=2)
    assert list(series.index) == ["a", "b"]
    assert list(series.values) == [0.3, 0.5]


def test_line_data_indexes_by_x():
    frame = pd.DataFrame({"period": ["d1", "d2"], "sessions": [10, 20]})
    out = line_data(frame, x="period")
    assert list(out.index) == ["d1", "d2"]
    assert "sessions" in out.columns


def test_line_data_drops_non_numeric_columns():
    """session_trend 프레임엔 요일 같은 문자열 열이 섞여 있다 — 선 차트는 수치만 그린다."""
    frame = pd.DataFrame({
        "period": ["d1", "d2"],
        "sessions": [10, 20],
        "weekday": ["월", "화"],
    })
    out = line_data(frame, x="period")
    assert "sessions" in out.columns
    assert "weekday" not in out.columns


def test_heatmap_pivot_makes_from_by_to_grid():
    frame = pd.DataFrame({
        "from_state": ["a", "a", "b"],
        "to_state": ["a", "b", "a"],
        "cnt": [1, 2, 3],
    })
    grid = heatmap_pivot(frame, "from_state", "to_state", "cnt")
    assert grid.loc["a", "b"] == 2
    assert grid.loc["b", "a"] == 3


def _community_frame():
    """a·b 는 군집 0, c 는 군집 1."""
    return pd.DataFrame({"state": ["a", "b", "c"], "community": [0, 0, 1]})


def _community_viz(edges):
    return {"kind": "graph", "x": "state", "group": "community", "edges": edges}


def _node_fillcolor(dot: str, state: str) -> str:
    line = next(l for l in dot.splitlines() if f'"{state}" [fillcolor=' in l)
    return line.split('fillcolor="')[1].split('"')[0]


def _edge_penwidth(dot: str, u: str, v: str) -> float:
    line = next(l for l in dot.splitlines() if f'"{u}" -- "{v}"' in l)
    return float(line.split("penwidth=")[1].split("]")[0])


def test_graph_dot_opens_an_undirected_graphviz_block():
    dot = graph_dot(_community_frame(), _community_viz([]))
    assert "graph G {" in dot


def test_graph_dot_emits_one_quoted_node_line_per_state():
    dot = graph_dot(_community_frame(), _community_viz([]))
    for state in ["a", "b", "c"]:
        assert f'"{state}" [fillcolor=' in dot
    assert dot.count("fillcolor=") == 3


def test_graph_dot_gives_the_same_community_the_same_color():
    dot = graph_dot(_community_frame(), _community_viz([]))
    assert _node_fillcolor(dot, "a") == _node_fillcolor(dot, "b")


def test_graph_dot_gives_different_communities_different_colors():
    dot = graph_dot(_community_frame(), _community_viz([]))
    assert _node_fillcolor(dot, "a") != _node_fillcolor(dot, "c")


def test_graph_dot_draws_each_edge_with_a_penwidth():
    edges = [["a", "b", 5.0], ["b", "c", 1.0]]
    dot = graph_dot(_community_frame(), _community_viz(edges))
    assert '"a" -- "b" [penwidth=' in dot
    assert '"b" -- "c" [penwidth=' in dot
    assert dot.count("penwidth=") == 2


def test_graph_dot_makes_the_heaviest_edge_thicker():
    edges = [["a", "b", 5.0], ["b", "c", 1.0]]
    dot = graph_dot(_community_frame(), _community_viz(edges))
    assert _edge_penwidth(dot, "a", "b") > _edge_penwidth(dot, "b", "c")

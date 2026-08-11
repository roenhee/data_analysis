import pandas as pd

from api.charts import chart_kind, bar_chart, line_chart, heatmap_chart, graph_dot


def test_chart_kind_reads_viz():
    assert chart_kind({"kind": "bar", "x": "state"}) == "bar"


def test_graph_falls_back_to_table_in_this_plan():
    """graph(networkx)는 3계획서. 지금은 표로."""
    assert chart_kind({"kind": "graph", "x": "state"}) == "table"


def test_missing_kind_is_table():
    assert chart_kind({}) == "table"


def test_bar_chart_is_a_bar_encoding_x_and_y():
    frame = pd.DataFrame({"state": ["a", "b", "c"], "pagerank": [0.3, 0.5, 0.2]})
    spec = bar_chart(frame, x="state", y="pagerank", top=3).to_dict()
    assert spec["mark"]["type"] == "bar"
    assert spec["encoding"]["x"]["field"] == "state"
    assert spec["encoding"]["y"]["field"] == "pagerank"


def test_bar_chart_limits_to_top():
    frame = pd.DataFrame({"state": list("abcde"), "v": [5, 4, 3, 2, 1]})
    ch = bar_chart(frame, x="state", y="v", top=2)
    assert len(ch.data) == 2


def test_bar_chart_sorts_by_value_descending():
    frame = pd.DataFrame({"state": ["a", "b"], "v": [1.0, 2.0]})
    spec = bar_chart(frame, x="state", y="v", top=2).to_dict()
    assert spec["encoding"]["x"]["sort"] == "-y"


def test_line_chart_folds_numeric_columns_into_series():
    """session_trend 처럼 수치 열이 여럿이면 색으로 구분한 여러 선이 된다."""
    frame = pd.DataFrame({"period": ["d1", "d2"], "sessions": [10, 20], "pv": [30, 40]})
    spec = line_chart(frame, x="period").to_dict()
    assert spec["mark"]["type"] == "line"
    assert spec["encoding"]["color"]["field"] == "series"


def test_line_chart_drops_non_numeric_columns():
    """문자열 열(요일 등)은 선으로 그리지 않는다."""
    frame = pd.DataFrame({"period": ["d1", "d2"], "sessions": [10, 20], "weekday": ["월", "화"]})
    ch = line_chart(frame, x="period")
    assert set(ch.data["series"].unique()) == {"sessions"}


def test_heatmap_chart_is_a_rect_mark_with_color_value():
    frame = pd.DataFrame({
        "from_state": ["a", "a", "b"], "to_state": ["a", "b", "a"], "cnt": [1, 2, 3],
    })
    spec = heatmap_chart(frame, x="from_state", to="to_state", value="cnt").to_dict()
    assert spec["mark"]["type"] == "rect"
    assert spec["encoding"]["x"]["field"] == "from_state"
    assert spec["encoding"]["y"]["field"] == "to_state"
    assert spec["encoding"]["color"]["field"] == "cnt"


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

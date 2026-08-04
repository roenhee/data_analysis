import pandas as pd

from dashboard.charts import chart_kind, bar_data, line_data, heatmap_pivot


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


def test_heatmap_pivot_makes_from_by_to_grid():
    frame = pd.DataFrame({
        "from_state": ["a", "a", "b"],
        "to_state": ["a", "b", "a"],
        "cnt": [1, 2, 3],
    })
    grid = heatmap_pivot(frame, "from_state", "to_state", "cnt")
    assert grid.loc["a", "b"] == 2
    assert grid.loc["b", "a"] == 3

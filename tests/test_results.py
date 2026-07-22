import pandas as pd

from data_layer.results import list_results, publish_result, read_result


def _data():
    return pd.DataFrame(
        {"from_state": ["A", "A", "B"], "to_state": ["B", "A", "A"], "p": [0.6, 0.4, 1.0]}
    )


def test_publish_writes_parquet_json_and_index(config):
    rid = publish_result(
        config,
        run_id="run1",
        skill="markov",
        analysis_type="transition_matrix",
        title="전이 히트맵",
        data=_data(),
        viz={"chart_type": "heatmap", "encoding": {"x": "from_state", "y": "to_state", "value": "p"}},
        params={"window": ["2026-01-05", "2026-02-01"], "seed": 7},
        config_version="cfg1",
        insight="홈탭→뉴스뷰 전이가 강함",
        created_at="2026-07-22T00:00:00Z",
    )
    assert (config.results_dir / f"{rid}.parquet").exists()
    assert (config.results_dir / f"{rid}.json").exists()

    idx = list_results(config)
    assert len(idx) == 1
    assert idx[0]["id"] == rid
    assert idx[0]["run_id"] == "run1"
    assert idx[0]["analysis_type"] == "transition_matrix"


def test_read_result_returns_data_and_envelope(config):
    rid = publish_result(
        config, run_id="run1", skill="markov", analysis_type="transition_matrix",
        title="전이 히트맵", data=_data(),
        viz={"chart_type": "heatmap", "encoding": {"x": "from_state", "y": "to_state", "value": "p"}},
        params={"seed": 7}, config_version="cfg1", insight="i", caveats="c",
        created_at="2026-07-22T00:00:00Z",
    )
    df, env = read_result(config, rid)
    assert list(df.columns) == ["from_state", "to_state", "p"]
    assert len(df) == 3
    assert env["title"] == "전이 히트맵"
    assert env["viz"]["chart_type"] == "heatmap"
    assert env["insight"] == "i"
    assert env["caveats"] == "c"
    assert env["config_version"] == "cfg1"
    assert [c["name"] for c in env["columns"]] == ["from_state", "to_state", "p"]


def test_list_results_filters_by_run(config):
    common = dict(
        skill="markov", data=_data(),
        viz={"chart_type": "table", "encoding": {}}, params={}, config_version="cfg1",
        created_at="t",
    )
    publish_result(config, run_id="runA", analysis_type="t1", title="a", **common)
    publish_result(config, run_id="runB", analysis_type="t2", title="b", **common)
    assert {r["run_id"] for r in list_results(config)} == {"runA", "runB"}
    assert len(list_results(config, run_id="runA")) == 1


import data_layer


def test_public_api_roundtrip(config):
    rid = data_layer.publish_result(
        config, run_id="run1", skill="markov", analysis_type="transition_matrix",
        title="t", data=_data(),
        viz={"chart_type": "heatmap", "encoding": {"x": "from_state", "y": "to_state", "value": "p"}},
        params={"seed": 7},
        config_version=data_layer.config_version({"cutoff": 0.95}, {"timeout_min": 30}),
        created_at="t0",
    )
    listed = data_layer.list_results(config, run_id="run1")
    assert len(listed) == 1 and listed[0]["id"] == rid
    df, env = data_layer.read_result(config, rid)
    assert len(df) == 3 and env["viz"]["chart_type"] == "heatmap"
    assert len(env["config_version"]) == 16

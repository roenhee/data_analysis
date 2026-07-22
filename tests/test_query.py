import pandas as pd

from data_layer.manifest import Manifest
from data_layer.query import run


def test_run_local_computes_and_caches(config):
    events = pd.DataFrame(
        {"from_state": ["A", "A", "B"], "to_state": ["B", "B", "A"]}
    )
    events.to_parquet(config.events_dir / "e.parquet")
    sql = (
        "SELECT from_state, to_state, COUNT(*) AS cnt "
        "FROM read_parquet('{p}') GROUP BY 1,2 ORDER BY 1,2"
    ).format(p=str(config.events_dir / "e.parquet"))

    df = run(config, sql, source_version="v1", config_version="c1",
             source_summary="transitions", date_range=["2026-01-05", "2026-01-06"])
    assert df.loc[df["from_state"] == "A", "cnt"].iloc[0] == 2

    m = Manifest.load(config.manifest_path)
    assert len(m.data["results"]) == 1
    assert m.data["results"][0]["source_summary"] == "transitions"


def test_run_returns_cached_without_recompute(config):
    events = pd.DataFrame({"x": [1, 2, 3]})
    events.to_parquet(config.events_dir / "e.parquet")
    sql = "SELECT SUM(x) AS s FROM read_parquet('{p}')".format(
        p=str(config.events_dir / "e.parquet")
    )
    first = run(config, sql, source_version="v1", config_version="c1")
    assert first["s"].iloc[0] == 6

    (config.events_dir / "e.parquet").unlink()
    second = run(config, sql, source_version="v1", config_version="c1")
    assert second["s"].iloc[0] == 6


def test_refresh_recomputes(config):
    events = pd.DataFrame({"x": [1, 2, 3]})
    events.to_parquet(config.events_dir / "e.parquet")
    sql = "SELECT SUM(x) AS s FROM read_parquet('{p}')".format(
        p=str(config.events_dir / "e.parquet")
    )
    run(config, sql, source_version="v1", config_version="c1")
    pd.DataFrame({"x": [10]}).to_parquet(config.events_dir / "e.parquet")
    out = run(config, sql, source_version="v1", config_version="c1", refresh=True)
    assert out["s"].iloc[0] == 10

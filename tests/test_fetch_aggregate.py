import pandas as pd

from data_layer.fetch_aggregate import fetch_aggregate
from data_layer.manifest import Manifest
from data_layer.sources import SourceDef


def _src():
    return SourceDef(
        id="events", kind="trino", host="h", port=8443,
        catalog="c", schema="s", table="t", auth_ref="TIARA",
        column_map={"app_user_id": "user.app_user_id"},
    )


def test_fetch_aggregate_caches_and_skips_refetch(config):
    calls = {"n": 0}

    def fake_query(source, sql):
        calls["n"] += 1
        return pd.DataFrame({"period": ["2026-01-05"], "uv": [10]})

    df1 = fetch_aggregate(config, _src(), "SELECT 1", query_fn=fake_query)
    df2 = fetch_aggregate(config, _src(), "SELECT 1", query_fn=fake_query)
    assert calls["n"] == 1                 # 2회차는 캐시 히트
    assert list(df1["uv"]) == [10]
    assert list(df2["uv"]) == [10]

    m = Manifest.load(config.manifest_path)
    results = m.data["results"]
    assert any(r["hash"].startswith("agg_") for r in results)
    assert results[0]["rows"] == 1


def test_fetch_aggregate_refresh_reruns(config):
    calls = {"n": 0}

    def fake_query(source, sql):
        calls["n"] += 1
        return pd.DataFrame({"uv": [calls["n"]]})

    fetch_aggregate(config, _src(), "SELECT 1", query_fn=fake_query)
    df = fetch_aggregate(config, _src(), "SELECT 1", refresh=True, query_fn=fake_query)
    assert calls["n"] == 2
    assert list(df["uv"]) == [2]

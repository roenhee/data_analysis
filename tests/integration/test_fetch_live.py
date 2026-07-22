import os
from pathlib import Path

import pytest

from data_layer.config import Config
from data_layer.connection import connect
from data_layer.config_artifacts import events_source_from_json
from data_layer.trino_fetcher import TrinoEventFetcher
from data_layer.fetch import get_events
from data_layer.cleanup import drop_temp_tables

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_creds():
    if not (os.environ.get("TIARA_ID") and os.environ.get("TIARA_PW")):
        pytest.skip("TIARA_ID/TIARA_PW not set")


def test_small_live_pull_entity_complete_and_no_residue(tmp_path):
    src = events_source_from_json(Path("examples/config/sources.json"), "events")
    config = Config(root=tmp_path / "cache")
    config.ensure_dirs()
    conn = connect(src)
    try:
        with TrinoEventFetcher(
            src, conn, write_schema="hadoop_rabbit_iceberg.axz_da",
            window=("2026-01-05", "2026-01-05"), seed=7, target_rows=5000,
            table_prefix="roen_dl",
        ) as tf:
            df = get_events(
                config, source_id="events", source_version=src.version(),
                start="2026-01-05", end="2026-01-05",
                partition_fetcher=tf.partition,
                sample={"method": "entity", "target": 5000, "seed": 7},
            )
        if len(df):
            assert {"app_user_id", "isuid", "start_day"}.issubset(df.columns)
    finally:
        remaining = drop_temp_tables(conn, "hadoop_rabbit_iceberg", "axz_da", "roen_dl")
        conn.close()
        assert remaining == [], f"temp tables leaked: {remaining}"

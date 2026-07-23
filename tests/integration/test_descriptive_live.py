import os
from pathlib import Path

import pytest

from data_layer.config import Config
from data_layer.config_artifacts import events_source_from_json
from data_layer.results import read_result
from skills.descriptive.run import run_analysis

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_creds():
    if not (os.environ.get("TIARA_ID") and os.environ.get("TIARA_PW")):
        pytest.skip("TIARA_ID/TIARA_PW not set")


def test_uv_pv_live_smoke(tmp_path):
    src = events_source_from_json(Path("examples/config/sources.json"), "events")
    config = Config(root=tmp_path / "cache")
    config.ensure_dirs()
    rid = run_analysis(
        config, src, "uv_pv_by_period",
        params={"window": ["2026-01-05", "2026-01-05"], "grain": "day",
                "breakdown": ["app_version"]},
        run_id="live", config_version="live",
    )
    df, env = read_result(config, rid)
    assert {"period", "app_version", "uv", "pv"}.issubset(df.columns)
    assert "전수집계(비샘플)" in env["caveats"]

"""실 Trino 스모크. 크레덴셜이 없으면 skip한다."""
import os
from pathlib import Path

import pytest

from analytics.cube.builder import build_cubes, build_state_dict
from data_layer.config import Config
from data_layer.sources import load_sources

pytestmark = pytest.mark.integration

DAY = "2026-07-27"
SERVICES = ["weather"]  # 작은 서비스로 스모크 비용을 낮춘다
SOURCES = Path("examples/config/sources.json")


@pytest.fixture(autouse=True)
def _require_creds():
    if not (os.environ.get("TIARA_ID") and os.environ.get("TIARA_PW")):
        pytest.skip("TIARA_ID/TIARA_PW not set — skipping live cube test")


def test_state_dict_and_cubes_build_against_live_trino(tmp_path):
    config = Config(root=tmp_path / "cache")
    config.ensure_dirs()

    sd = build_state_dict(config, window=(DAY, DAY), services=SERVICES, min_count=1)
    assert sd.screens, "화면이 하나도 채택되지 않았다 — 컷 또는 필터를 확인하라"
    assert sd.app_versions

    written = build_cubes(
        config, state_dict=sd, window=(DAY, DAY), services=SERVICES,
        source_version=load_sources(SOURCES)["events"].version(),
    )
    assert len(written) == 3

    import pandas as pd

    session = pd.read_parquet(next(p for p in written if "session" in str(p)))
    assert {"sessions", "uv", "pv", "duration_sum"} <= set(session.columns)
    assert session["sessions"].sum() > 0

    transition = pd.read_parquet(next(p for p in written if "transition" in str(p)))
    assert {"from_state", "to_state", "cnt"} <= set(transition.columns)
    assert (transition["from_state"] == "START").any()
    assert (transition["to_state"] == "EXIT").any()

    quality = pd.read_parquet(next(p for p in written if "quality" in str(p)))
    assert {"check_name", "violated", "total"} <= set(quality.columns)


def test_second_build_is_a_noop(tmp_path):
    config = Config(root=tmp_path / "cache")
    config.ensure_dirs()
    sd = build_state_dict(config, window=(DAY, DAY), services=SERVICES, min_count=1)
    sv = load_sources(SOURCES)["events"].version()
    kw = dict(config=config, state_dict=sd, window=(DAY, DAY), services=SERVICES,
              source_version=sv)
    build_cubes(**kw)
    assert build_cubes(**kw) == []

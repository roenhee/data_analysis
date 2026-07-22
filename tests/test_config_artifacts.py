import json
from pathlib import Path

from data_layer.config_artifacts import load_dictionary, events_source_from_json


def test_events_source_from_examples():
    src = events_source_from_json(Path("examples/config/sources.json"), "events")
    assert src.catalog == "bigdata_omega_common_iceberg"
    assert src.schema == "axz_tiara"
    assert src.table == "all_tiara_i"
    assert src.auth_ref == "TIARA"
    assert "action_name" in src.column_map
    assert any("service_code" in f or "action" in f for f in src.filters)


def test_load_dictionary(tmp_path):
    p = tmp_path / "dict.json"
    p.write_text(json.dumps({"cutoff": 0.95, "vocabulary": ["A"], "mapping": {"A": "A"}}))
    d = load_dictionary(p)
    assert d["cutoff"] == 0.95
    assert d["mapping"]["A"] == "A"

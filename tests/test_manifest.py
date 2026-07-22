import json

from data_layer.manifest import Manifest


def test_new_manifest_is_empty(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    assert m.event_start_days() == set()
    assert m.has_result("abc") is False


def test_add_event_partition_and_reload(tmp_path):
    path = tmp_path / "manifest.json"
    m = Manifest.load(path)
    m.add_event_partition(
        start_day="2026-01-05",
        entities=10,
        rows=100,
        size_bytes=2048,
        source_id="events",
        source_query_hash="qh",
        sample={"method": "entity", "target": 1_000_000, "seed": 7},
        window_bounds=["2026-01-05", "2026-02-01"],
    )
    m.save()

    m2 = Manifest.load(path)
    assert m2.event_start_days() == {"2026-01-05"}
    ev = m2.data["events"][0]
    assert ev["sample"]["seed"] == 7
    assert ev["window_bounds"] == ["2026-01-05", "2026-02-01"]


def test_add_and_check_result(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    m.add_result(
        result_hash="h1",
        source_summary="transition counts",
        date_range=["2026-01-05", "2026-02-01"],
        params={"k": 5},
        config_version="cfg1",
        rows=42,
        size_bytes=512,
    )
    assert m.has_result("h1") is True
    assert m.has_result("nope") is False


def test_add_dim(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    m.add_dim(name="demographics", source_id="demo", key="app_user_id", rows=999)
    assert m.data["dims"][0]["name"] == "demographics"


def test_add_event_partition_dedups_by_start_day(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    kw = dict(entities=1, rows=1, size_bytes=1, source_id="events",
              source_query_hash="qh", sample={}, window_bounds=[])
    m.add_event_partition(start_day="2026-01-05", **kw)
    m.add_event_partition(start_day="2026-01-05", **{**kw, "rows": 999})
    evs = [e for e in m.data["events"] if e["start_day"] == "2026-01-05"]
    assert len(evs) == 1
    assert evs[0]["rows"] == 999


def test_add_result_dedups_by_hash(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    kw = dict(source_summary="s", date_range=[], params={}, config_version="c",
              rows=1, size_bytes=1)
    m.add_result(result_hash="h1", **kw)
    m.add_result(result_hash="h1", **{**kw, "rows": 5})
    hits = [r for r in m.data["results"] if r["hash"] == "h1"]
    assert len(hits) == 1
    assert hits[0]["rows"] == 5


def test_add_dim_dedups_by_name(tmp_path):
    m = Manifest.load(tmp_path / "manifest.json")
    m.add_dim(name="demographics", source_id="a", key="app_user_id", rows=1)
    m.add_dim(name="demographics", source_id="b", key="app_user_id", rows=2)
    hits = [d for d in m.data["dims"] if d["name"] == "demographics"]
    assert len(hits) == 1
    assert hits[0]["rows"] == 2


def test_results_and_dims_survive_save_reload(tmp_path):
    path = tmp_path / "manifest.json"
    m = Manifest.load(path)
    m.add_result(result_hash="h1", source_summary="s", date_range=["a", "b"],
                 params={"k": 5}, config_version="c", rows=1, size_bytes=1)
    m.add_dim(name="demographics", source_id="demo", key="app_user_id", rows=9)
    m.save()
    m2 = Manifest.load(path)
    assert m2.has_result("h1") is True
    assert m2.data["results"][0]["params"] == {"k": 5}
    assert m2.data["dims"][0]["name"] == "demographics"


def test_load_backfills_missing_keys(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"events": [{"start_day": "2026-01-05"}]}))
    m = Manifest.load(path)
    assert m.data["dims"] == []
    assert m.data["results"] == []
    assert m.data["config"] == {}
    assert m.event_start_days() == {"2026-01-05"}

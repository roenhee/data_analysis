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

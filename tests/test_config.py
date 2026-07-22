from pathlib import Path

from data_layer.config import Config


def test_config_paths(tmp_path):
    c = Config(root=tmp_path / "cache")
    assert c.events_dir == tmp_path / "cache" / "events"
    assert c.dims_dir == tmp_path / "cache" / "dims"
    assert c.results_dir == tmp_path / "cache" / "results"
    assert c.config_dir == tmp_path / "cache" / "config"
    assert c.manifest_path == tmp_path / "cache" / "manifest.json"


def test_ensure_dirs_creates_all(tmp_path):
    c = Config(root=tmp_path / "cache")
    c.ensure_dirs()
    for d in (c.events_dir, c.dims_dir, c.results_dir, c.config_dir):
        assert d.is_dir()


def test_from_env_defaults_to_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_LAYER_CACHE", raising=False)
    c = Config.from_env()
    assert c.root == Path("cache")
    monkeypatch.setenv("DATA_LAYER_CACHE", str(tmp_path / "x"))
    assert Config.from_env().root == tmp_path / "x"

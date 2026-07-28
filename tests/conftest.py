import pytest

try:
    from data_layer.config import Config
    _HAS_CONFIG = True
except Exception:
    _HAS_CONFIG = False

if _HAS_CONFIG:

    @pytest.fixture
    def config(tmp_path):
        c = Config(root=tmp_path / "cache")
        c.ensure_dirs()
        return c

import pandas as pd
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


@pytest.fixture
def sample_events():
    return pd.DataFrame(
        {
            "app_user_id": ["u1", "u1", "u1", "u2", "u2"],
            "isuid": ["s1", "s1", "s1", "s2", "s2"],
            "access_time": [
                "2026-01-05 23:59:50",
                "2026-01-06 00:00:10",
                "2026-01-06 00:00:30",
                "2026-01-06 09:00:00",
                "2026-01-06 09:01:00",
            ],
            "access_timestamp": [
                1767625190000,
                1767625210000,
                1767625230000,
                1767657600000,
                1767657660000,
            ],
            "day": ["2026-01-05", "2026-01-06", "2026-01-06", "2026-01-06", "2026-01-06"],
            "action_name": ["홈탭_진입", "뉴스_1슬롯", "앱종료", "홈탭_진입", "앱종료"],
        }
    )

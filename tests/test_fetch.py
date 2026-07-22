import pandas as pd

from data_layer.fetch import get_events, missing_start_days, read_partitions
from data_layer.manifest import Manifest


def test_missing_start_days_returns_gap_only():
    existing = {"2026-01-05", "2026-01-06"}
    assert missing_start_days(existing, "2026-01-05", "2026-01-08") == [
        "2026-01-07",
        "2026-01-08",
    ]


def test_missing_start_days_all_present():
    existing = {"2026-01-05", "2026-01-06"}
    assert missing_start_days(existing, "2026-01-05", "2026-01-06") == []


def _partition_df(day, user):
    return pd.DataFrame(
        {
            "app_user_id": [user, user],
            "isuid": [f"{user}s", f"{user}s"],
            "access_time": [f"{day} 10:00:00", f"{day} 10:01:00"],
            "access_timestamp": [1, 2],
            "day": [day, day],
            "action_name": ["홈탭_진입", "앱종료"],
        }
    )


def test_read_partitions_unions_existing_days(config):
    for day, user in [("2026-01-05", "u1"), ("2026-01-06", "u2")]:
        _partition_df(day, user).to_parquet(
            config.events_dir / f"start_day={day}.parquet"
        )
    df = read_partitions(config, ["2026-01-05", "2026-01-06"])
    assert len(df) == 4
    assert set(df["app_user_id"]) == {"u1", "u2"}


def test_get_events_fetches_only_missing_and_records_sample(config):
    calls = []

    def fake_fetcher(start_day):
        calls.append(start_day)
        return pd.DataFrame(
            {
                "app_user_id": ["u1", "u1"],
                "isuid": ["s1", "s1"],
                "access_time": ["2026-01-05 23:59:50", "2026-01-06 00:00:10"],
                "access_timestamp": [1, 2],
                "day": ["2026-01-05", "2026-01-06"],
                "action_name": ["홈탭_진입", "앱종료"],
            }
        )

    df = get_events(
        config,
        source_id="events",
        source_version="v1",
        start="2026-01-05",
        end="2026-01-05",
        partition_fetcher=fake_fetcher,
        sample={"method": "entity", "target": 1_000_000, "seed": 7},
    )
    assert calls == ["2026-01-05"]
    assert len(df) == 2

    m = Manifest.load(config.manifest_path)
    assert m.event_start_days() == {"2026-01-05"}
    assert m.data["events"][0]["sample"]["seed"] == 7

    calls.clear()
    get_events(
        config,
        source_id="events",
        source_version="v1",
        start="2026-01-05",
        end="2026-01-05",
        partition_fetcher=fake_fetcher,
        sample={"method": "entity", "target": 1_000_000, "seed": 7},
    )
    assert calls == []

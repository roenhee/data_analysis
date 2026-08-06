"""cube_store: 기간 계산·상한·LRU·실제 로드."""
import pytest

from api import cube_store

_STATE_DICT_VERSION = "sd_2ab5ec25e750dda2"
_SERVICES = ("top", "media", "entertain", "sports", "content_v", "search")


def test_period_days_counts_inclusive():
    assert cube_store.period_days("2026-07-14", "2026-07-14") == 1
    assert cube_store.period_days("2026-07-14", "2026-07-28") == 15


def test_load_rejects_over_hard_limit():
    with pytest.raises(cube_store.PeriodTooLongError):
        cube_store.load(("session",), "2026-01-01", "2026-12-31",
                        ("top",), _STATE_DICT_VERSION)


def test_load_rejects_reversed_range():
    with pytest.raises(ValueError):
        cube_store.load(("session",), "2026-07-16", "2026-07-14",
                        _SERVICES, _STATE_DICT_VERSION)


def test_load_reads_local_session_cube():
    cubes = cube_store.load(("session",), "2026-07-14", "2026-07-16",
                            _SERVICES, _STATE_DICT_VERSION)
    assert cubes.session is not None
    assert set(cubes.present_dates) <= {"2026-07-14", "2026-07-15", "2026-07-16"}
    assert cubes.state_dict_version == _STATE_DICT_VERSION


def test_load_is_cached_same_object():
    args = (("session",), "2026-07-14", "2026-07-16", _SERVICES, _STATE_DICT_VERSION)
    assert cube_store.load(*args) is cube_store.load(*args)

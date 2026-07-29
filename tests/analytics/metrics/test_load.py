import pandas as pd
import pytest

from analytics.metrics.load import IncompleteCubeError, LoadedCube, load_cube

KEY = dict(
    source_version="sv1",
    state_dict_version="sd_abc",
    axes=("period", "os"),
    cube_name="session",
    sql_hash="lh_abc",
)


def _write(config, date, rows):
    from analytics.cube.store import write_cube
    write_cube(config, pd.DataFrame(rows), date=date, **KEY)


def test_loads_the_requested_dates(config):
    _write(config, "2026-07-26", {"sessions": [1]})
    _write(config, "2026-07-27", {"sessions": [2]})
    got = load_cube(config, dates=["2026-07-26", "2026-07-27"], **KEY)
    assert isinstance(got, LoadedCube)
    assert got.frame["sessions"].sum() == 3
    assert got.present_dates == ["2026-07-26", "2026-07-27"]
    assert got.missing_dates == []
    assert got.is_complete is True


def test_reports_missing_dates_instead_of_hiding_them(config):
    # read_cube 는 일부만 없으면 조용히 읽는다. 그 조용함이 여기서 끝나야 한다.
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-26", "2026-07-27"], **KEY)
    assert got.missing_dates == ["2026-07-27"]
    assert got.is_complete is False


def test_require_complete_raises_on_a_partial_build(config):
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-26", "2026-07-27"], **KEY)
    with pytest.raises(IncompleteCubeError, match="2026-07-27"):
        got.require_complete()


def test_require_complete_passes_when_every_date_is_present(config):
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-26"], **KEY)
    assert got.require_complete() is got


def test_missing_everything_still_raises_cube_not_built(config):
    from analytics.cube.store import CubeNotBuiltError
    with pytest.raises(CubeNotBuiltError):
        load_cube(config, dates=["2026-07-26"], **KEY)


def test_duplicate_dates_are_requested_once(config):
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-26", "2026-07-26"], **KEY)
    assert got.frame["sessions"].sum() == 1
    assert got.present_dates == ["2026-07-26"]


def test_dates_are_reported_in_sorted_order(config):
    _write(config, "2026-07-27", {"sessions": [1]})
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-27", "2026-07-26"], **KEY)
    assert got.present_dates == ["2026-07-26", "2026-07-27"]

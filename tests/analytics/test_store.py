import pandas as pd

import pytest

from analytics.cube.store import (
    CubeNotBuiltError,
    cube_key,
    cube_path,
    has_cube,
    read_cube,
    write_cube,
)

KW = dict(
    source_version="sv1",
    state_dict_version="sd_abc",
    axes=("period", "os"),
    cube_name="transition",
)


def test_cube_key_is_stable():
    assert cube_key(**KW) == cube_key(**KW)


def test_cube_key_changes_with_source_version():
    assert cube_key(**KW) != cube_key(**{**KW, "source_version": "sv2"})


def test_cube_key_changes_with_state_dict_version():
    assert cube_key(**KW) != cube_key(**{**KW, "state_dict_version": "sd_xyz"})


def test_cube_key_changes_with_axes():
    assert cube_key(**KW) != cube_key(**{**KW, "axes": ("period",)})


def test_cube_key_changes_with_cube_name():
    assert cube_key(**KW) != cube_key(**{**KW, "cube_name": "session"})


def test_cube_path_partitions_by_date_under_the_key(config):
    path = cube_path(config, date="2026-07-27", **KW)
    assert path.name == "date=2026-07-27.parquet"
    assert cube_key(**KW) in str(path)
    assert "transition" in str(path)


def test_has_cube_is_false_before_write_and_true_after(config):
    assert has_cube(config, date="2026-07-27", **KW) is False
    write_cube(config, pd.DataFrame({"cnt": [1]}), date="2026-07-27", **KW)
    assert has_cube(config, date="2026-07-27", **KW) is True


def test_write_cube_roundtrips_the_frame(config):
    df = pd.DataFrame({"from_state": ["a"], "to_state": ["b"], "cnt": [3]})
    path = write_cube(config, df, date="2026-07-27", **KW)
    assert pd.read_parquet(path).equals(df)


def test_different_dates_do_not_collide(config):
    write_cube(config, pd.DataFrame({"cnt": [1]}), date="2026-07-27", **KW)
    assert has_cube(config, date="2026-07-28", **KW) is False


def test_read_cube_concatenates_the_requested_dates(config):
    write_cube(config, pd.DataFrame({"cnt": [1]}), date="2026-07-27", **KW)
    write_cube(config, pd.DataFrame({"cnt": [2]}), date="2026-07-28", **KW)
    df = read_cube(config, dates=["2026-07-27", "2026-07-28"], **KW)
    assert sorted(df["cnt"].tolist()) == [1, 2]


def test_read_cube_skips_dates_that_were_never_built(config):
    write_cube(config, pd.DataFrame({"cnt": [1]}), date="2026-07-27", **KW)
    df = read_cube(config, dates=["2026-07-27", "2026-07-28"], **KW)
    assert df["cnt"].tolist() == [1]


def test_read_cube_raises_when_nothing_was_built(config):
    # 빈 프레임을 돌려주면 미빌드와 '데이터 없음'이 구분되지 않는다.
    with pytest.raises(CubeNotBuiltError, match="no cube built"):
        read_cube(config, dates=["2026-07-27"], **KW)

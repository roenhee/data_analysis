"""`CubeSet` 이 행동층 큐브 3개를 싣는다. 기본이 `None` 이라 기존 호출은 그대로 돈다."""
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet
from analytics.analyses.cubes import ACTION_LAYER_CUBE_NAMES

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _action() -> pd.DataFrame:
    return pd.DataFrame([
        {**AXES, "screen": "top/a", "action_kind": "ClickContent",
         "layer1": "home_main", "layer2": "home_main>FEED", "cnt": 10},
        {**AXES, "period": "2026-07-28", "screen": "top/a",
         "action_kind": "ClickContent", "layer1": "home_main",
         "layer2": "home_main>FEED", "cnt": 20},
    ])


def _cond() -> pd.DataFrame:
    return pd.DataFrame([
        {"period": "2026-07-27", "service_type": "MA", "os": "android",
         "app_version": "9.5.1", "from_state": "top/a",
         "action_kind": "ClickContent", "to_state": "top/b", "cnt": 7},
        {"period": "2026-07-28", "service_type": "MA", "os": "android",
         "app_version": "9.5.1", "from_state": "top/a",
         "action_kind": "(no_click)", "to_state": "EXIT", "cnt": 3},
    ])


def _path() -> pd.DataFrame:
    return pd.DataFrame([
        {**AXES, "n": 3, "path": "top/a>top/b>top/c", "cnt": 5,
         "distinct_dropped": 0},
        {**AXES, "period": "2026-07-28", "n": 3, "path": "top/a>top/b>top/c",
         "cnt": 9, "distinct_dropped": 0},
    ])


def _cubes(**over) -> CubeSet:
    days = ["2026-07-27", "2026-07-28"]
    base = dict(session=None, transition=None, quality=None,
                state_dict_version="sd_abc", services=["top"],
                requested_dates=days, present_dates=days)
    return CubeSet(**{**base, **over})


def test_the_three_action_layer_cubes_are_named_in_one_place():
    """이름을 흩뿌리면 하나를 빠뜨린 채 배선이 끝난다."""
    assert ACTION_LAYER_CUBE_NAMES == ("action", "cond_transition", "path")


def test_a_cubeset_built_without_them_still_works():
    """기본이 `None` 이라 기존 호출 전부가 그대로 돈다."""
    got = _cubes()
    assert got.action is None
    assert got.cond_transition is None
    assert got.path is None


def test_the_new_cubes_are_carried():
    got = _cubes(action=_action(), cond_transition=_cond(), path=_path())
    assert len(got.action) == 2
    assert len(got.cond_transition) == 2
    assert len(got.path) == 2


def test_filtering_by_date_cuts_the_new_cubes_too():
    """안 자르면 봉투가 "없다" 고 적은 날짜의 행으로 숫자를 만든다."""
    got = _cubes(action=_action(), cond_transition=_cond(),
                 path=_path()).filter(dates=["2026-07-27"])
    assert got.action["cnt"].tolist() == [10]
    assert got.cond_transition["cnt"].tolist() == [7]
    assert got.path["cnt"].tolist() == [5]
    assert got.present_dates == ["2026-07-27"]


def test_filtering_by_an_axis_cuts_the_new_cubes_too():
    got = _cubes(action=_action(), cond_transition=_cond(),
                 path=_path()).filter(app_version="9.5.1")
    assert len(got.action) == 2
    assert len(got.cond_transition) == 2


def test_an_axis_missing_from_a_cube_is_skipped_not_an_error():
    """`cond_transition` 은 4축이라 `gender` 가 없다. 없는 축 조건은 건너뛴다."""
    got = _cubes(action=_action(), cond_transition=_cond()).filter(gender="M")
    assert len(got.cond_transition) == 2   # 축이 없으므로 그대로
    assert len(got.action) == 2            # 축이 있고 M 이므로 그대로
    assert _cubes(action=_action()).filter(gender="F").action.empty

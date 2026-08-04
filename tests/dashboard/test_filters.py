import pandas as pd

from analytics.analyses.base import CubeSet
from dashboard.filters import cube_names_for, apply_segment


def test_cube_names_for_screen_analysis_is_default():
    from analytics.analyses.cubes import DEFAULT_CUBE_NAMES
    assert cube_names_for("screen_flow") == DEFAULT_CUBE_NAMES


def test_cube_names_for_action_analysis_includes_path():
    names = cube_names_for("path_ranking")
    assert "path" in names
    assert "transition" in names   # markov 는 transition 도 쓴다 → 전부 싣는다


def _cubes() -> CubeSet:
    edges = pd.DataFrame({
        "from_state": ["a", "a"], "to_state": ["b", "b"], "cnt": [1, 2],
        "service_type": ["MA", "MW"], "period": ["2026-07-27", "2026-07-27"],
    })
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def test_apply_segment_filters_axes_that_are_set():
    got = apply_segment(_cubes(), {"service_type": "MA", "os": ""})
    assert set(got.transition["service_type"]) == {"MA"}


def test_apply_segment_ignores_empty_axes():
    got = apply_segment(_cubes(), {"service_type": "", "os": ""})
    assert len(got.transition) == 2   # 아무것도 안 좁힘

"""화면 안의 클릭 분포 분석. 화면 안에서 정규화하는 것과 귀속 불가 비중이 요점이다."""
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _click(screen: str, kind: str, cnt: int, layer1: str = "home_main",
           layer2: str = "home_main>FEED") -> dict:
    return {**AXES, "screen": screen, "action_kind": kind,
            "layer1": layer1, "layer2": layer2, "cnt": cnt}


def _edge(f: str, t: str, cnt: int) -> dict:
    return {**AXES, "from_state": f, "to_state": t, "cnt": cnt,
            "dur_sum": float(cnt) * 10.0, "dur_n": cnt}


# 클릭 100건: top/a 60(ClickContent) + 30(Share), START 10.
# 화면 방문: top/a 50 (START 엣지 20 은 화면이 아니라 분모에 안 들어간다).
ACTIONS = [
    _click("top/a", "ClickContent", 60),
    _click("top/a", "Share", 30),
    _click("START", "AppLaunch", 10, layer1="other", layer2="other"),
]
EDGES = [_edge("START", "top/a", 20), _edge("top/a", "EXIT", 50)]


def _cubes(actions=ACTIONS, edges=EDGES) -> CubeSet:
    return CubeSet(
        session=None,
        transition=pd.DataFrame(edges) if edges is not None else None,
        quality=None, state_dict_version="sd_abc", services=["top"],
        requested_dates=["2026-07-27"], present_dates=["2026-07-27"],
        action=pd.DataFrame(actions),
    )


def test_one_row_per_screen_and_kind():
    got = get_analysis("click_distribution")(_cubes())
    assert {"screen", "action_kind", "cnt", "share"} <= set(got.frame.columns)
    assert len(got.frame) == 3


def test_the_share_is_within_the_screen():
    got = get_analysis("click_distribution")(_cubes()).frame.set_index(
        ["screen", "action_kind"]
    )
    assert got.loc[("top/a", "ClickContent"), "share"] == pytest.approx(60 / 90)
    assert got.loc[("top/a", "Share"), "share"] == pytest.approx(30 / 90)
    assert got.loc[("START", "AppLaunch"), "share"] == pytest.approx(1.0)


def test_the_grouping_axis_is_a_parameter():
    """`layer1` 로도 물을 수 있다 — 슬롯 단위 분포가 다른 질문이다."""
    got = get_analysis("click_distribution")(_cubes(), by=("layer1",))
    assert "layer1" in got.frame.columns
    assert "action_kind" not in got.frame.columns


def test_headline_clicks_is_the_total():
    got = get_analysis("click_distribution")(_cubes())
    assert got.headline["clicks"] == pytest.approx(100.0)


def test_headline_clicks_per_visit_joins_the_transition_cube():
    """공유 화면 이름의 회수분. 분모는 **화면** 방문이라 `START` 엣지를 빼야 한다."""
    got = get_analysis("click_distribution")(_cubes())
    # 화면에 귀속된 클릭 90 / 화면 방문 50
    assert got.headline["clicks_per_visit"] == pytest.approx(90 / 50)


def test_headline_clicks_per_visit_is_nan_without_the_transition_cube():
    """방문 수를 모르면 NaN 이다. 0 으로 채우면 "안 누른다" 와 섞인다."""
    got = get_analysis("click_distribution")(_cubes(edges=None))
    assert pd.isna(got.headline["clicks_per_visit"])
    assert got.headline["clicks"] == pytest.approx(100.0)


def test_headline_unattributed_share_is_in_the_headline_not_just_the_frame():
    """세그먼트끼리 이 비중이 다르면 분포 자체가 비교 불가다 — `dwell_coverage` 와 같은 이유."""
    got = get_analysis("click_distribution")(_cubes())
    assert got.headline["unattributed_share"] == pytest.approx(0.1)


def test_a_cube_without_the_action_frame_is_refused():
    cubes = _cubes()
    empty = CubeSet(session=None, transition=cubes.transition, quality=None,
                    state_dict_version="sd_abc", services=["top"],
                    requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="needs the action cube"):
        get_analysis("click_distribution")(empty)


def test_the_envelope_carries_the_unattributed_warning_when_it_is_large():
    """귀속 불가가 크면 화면별 분포가 대표성을 잃는다. 실측은 1.61% 라 안 걸린다."""
    heavy = [_click("top/a", "ClickContent", 40),
             _click("START", "AppLaunch", 60, layer1="other", layer2="other")]
    got = get_analysis("click_distribution")(_cubes(actions=heavy))
    assert "clicks_without_a_screen" in [
        w["check_name"] for w in got.envelope["warnings"]
    ]
    assert "clicks_without_a_screen" not in [
        w["check_name"] for w in get_analysis("click_distribution")(
            _cubes()
        ).envelope["warnings"]
    ]

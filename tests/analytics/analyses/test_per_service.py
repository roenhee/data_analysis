"""서비스별 분해. 합산이 서비스 범위 밖일 수 있다는 것이 요점이다."""
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet
from analytics.analyses.operators import per_service

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _edge(f: str, t: str, cnt: int) -> dict:
    return {**AXES, "from_state": f, "to_state": t, "cnt": cnt,
            "dur_sum": float(cnt) * 10.0, "dur_n": cnt}


# 실측 구조를 축소한 것: 세션이 두 서비스를 **오간다.**
#   START -> top/a -> top/b -> media/x -> top/a -> ...  (그리고 각자 EXIT 로도 나간다)
#
# 서비스별로 자르면 그 왕복이 사라지고 각 체인은 곧장 끝난다(top 1.75, media 1.00).
# 합친 체인에는 왕복이 있어서 **8.86** 이다 — 어느 서비스보다도 크다. 실큐브에서
# 합산 10.62 대 최대 8.08 로 나타나는 것과 같은 기제다.
#
# 두 슬라이스가 **각자 EXIT 로 가는 길을 가져야 한다.** 없으면 `screen_flow` 가
# `KeyError: unknown state: 'EXIT'` 로 죽고, 그러면 그 서비스 행이 NaN 이 되어
# `outside_range` 가 남은 한 줄만 보고 "범위 밖" 이라고 말한다 — 통과하지만 이유가 틀린다.
def _cubes() -> CubeSet:
    edges = pd.DataFrame([
        _edge("START", "top/a", 100),
        _edge("top/a", "top/b", 300),
        _edge("top/b", "media/x", 400),   # 서비스를 건너뛴다
        _edge("top/b", "EXIT", 100),
        _edge("media/x", "top/a", 350),   # 되돌아온다
        _edge("media/x", "EXIT", 50),
    ])
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd_abc", services=["top", "media"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def test_one_row_per_service():
    got = per_service(_cubes(), "screen_flow")
    assert got.frame["service"].tolist() == ["media", "top"]
    assert got.services == ["media", "top"]


def test_the_frame_carries_each_service_volume_and_share():
    got = per_service(_cubes(), "screen_flow")
    per = got.frame.set_index("service")
    # 화면에서 **출발한** 전이: top 800(300+400+100), media 400(350+50)
    assert per.loc["top", "cnt"] == pytest.approx(800.0)
    assert per.loc["media", "cnt"] == pytest.approx(400.0)
    assert per.loc["top", "share"] == pytest.approx(2 / 3)
    assert per.loc["media", "share"] == pytest.approx(1 / 3)


def test_each_headline_key_becomes_a_column():
    got = per_service(_cubes(), "screen_flow")
    assert "mean_expected_steps" in got.frame.columns
    assert "mean_exit_prob" in got.frame.columns


def test_the_frame_carries_the_other_share_next_to_the_metrics():
    """그 서비스의 값을 얼마나 믿을 수 있는지가 같은 줄에 있어야 한다.

    `/other` 는 여러 화면을 접은 가짜 화면이라, 비중이 크면 그 서비스의 기대 화면 수가
    치우친다. 표에서 두 열이 떨어져 있으면 소비자가 짝지어 읽지 않는다.
    """
    edges = pd.concat([_cubes().transition, pd.DataFrame([
        _edge("top/other", "top/a", 200),
    ])], ignore_index=True)
    lumped = CubeSet(session=None, transition=edges, quality=None,
                     state_dict_version="sd_abc", services=["top", "media"],
                     requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    per = per_service(lumped, "screen_flow").frame.set_index("service")
    # top 은 화면 출발 1000(800 + other 200) 중 200 이 `/other` 다
    assert per.loc["top", "other_share"] == pytest.approx(0.2)
    assert per.loc["media", "other_share"] == pytest.approx(0.0)


def test_the_slice_keeps_only_transitions_with_both_ends_in_the_service():
    """출발만 보고 자르면 다른 서비스 화면이 그 체인에 남아 값이 달라진다.

    top 슬라이스는 `START->top/a`, `top/a->top/b`, `top/b->EXIT` 셋이다. `top/b->media/x`
    를 남기면 `media/x` 가 나가는 길 없는 상태로 체인에 들어와 기대 화면 수가 발산한다.
    """
    per = per_service(_cubes(), "screen_flow").frame.set_index("service")
    assert per.loc["top", "mean_expected_steps"] == pytest.approx(1.75)
    assert per.loc["media", "mean_expected_steps"] == pytest.approx(1.00)


def test_a_pooled_value_above_the_service_range_is_flagged():
    """이게 이 연산자의 존재 이유다 — 실측에서 기대 화면 수 합산 10.62 > 최대 8.08 이었다."""
    got = per_service(_cubes(), "screen_flow")
    assert got.pooled["mean_expected_steps"] == pytest.approx(8.861111, abs=1e-6)
    assert got.outside_range["mean_expected_steps"] == pytest.approx((1.00, 1.75))
    assert got.pooled["mean_expected_steps"] > got.outside_range[
        "mean_expected_steps"
    ][1]


def test_a_pooled_value_below_the_service_range_is_also_flagged():
    """벗어나는 방향이 위쪽만이 아니다. 이탈확률은 합산이 서비스별 최소보다 **낮다.**"""
    got = per_service(_cubes(), "screen_flow")
    assert got.pooled["mean_exit_prob"] == pytest.approx(0.125)
    assert got.outside_range["mean_exit_prob"] == pytest.approx((0.25, 1.00))
    assert got.pooled["mean_exit_prob"] < got.outside_range["mean_exit_prob"][0]


def test_the_cross_service_share_is_reported():
    """서비스별로 자르면 서비스를 건너뛰는 전이가 사라진다. 얼마나 사라졌는지 말해야 한다.

    **분모가 `share` 와 다르다.** `share` 는 화면에서 *출발한* 전이(1200, `-> EXIT` 포함)
    기준이고, 이쪽은 화면에서 화면으로 간 전이(1050, `-> EXIT` 과 `START ->` 제외) 기준이다 —
    서비스를 건너뛰는지 물으려면 도착도 화면이어야 한다. 두 분모를 섞으면 물량이 조용히 틀린다.
    """
    got = per_service(_cubes(), "screen_flow")
    # 화면->화면 1050(300+400+350) 중 건너뛰는 것 750(400+350)
    assert got.cross_service_share == pytest.approx(750 / 1050)


def test_a_session_cube_analysis_is_refused_with_the_reason():
    """세션은 서비스로 못 가른다 — 44.7%가 여러 서비스에 걸쳐 있어 합이 부푼다."""
    sessions = CubeSet(session=pd.DataFrame([{**AXES, "sessions": 10, "uv": 5,
                                              "pv": 80, "events": 300,
                                              "duration_sum": 6000}]),
                       transition=None, quality=None, state_dict_version="sd_abc",
                       services=["top"], requested_dates=["2026-07-27"],
                       present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="cannot be split by service"):
        per_service(sessions, "session_trend")


def test_a_service_whose_analysis_raises_is_reported_as_nan_not_dropped():
    """한 서비스에서 분석이 죽어도 나머지는 낸다. 조용히 빠지면 표가 전수처럼 읽힌다."""
    got = per_service(_cubes(), "reachability", source="top/a", target="top/b")
    per = got.frame.set_index("service")
    assert pd.isna(per.loc["media", "p_hit_within_10"])
    assert "unknown source state" in per.loc["media", "error"]
    assert per.loc["top", "p_hit_within_10"] > 0

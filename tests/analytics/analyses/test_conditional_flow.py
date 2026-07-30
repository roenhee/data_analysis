"""어떤 행동이 다음 화면을 결정하는가. headline 이 조건부 상호정보량인 것이 요점이다."""
import numpy as np
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

AXES = dict(period="2026-07-27", service_type="MA", os="android",
            app_version="9.5.1")


def _row(f: str, kind: str, t: str, cnt: int) -> dict:
    return {**AXES, "from_state": f, "action_kind": kind, "to_state": t, "cnt": cnt}


def _edge(f: str, t: str, cnt: int) -> dict:
    return {**AXES, "gender": "M", "age_band": "50", "daypart": "12~17",
            "from_state": f, "to_state": t, "cnt": cnt,
            "dur_sum": float(cnt) * 10.0, "dur_n": cnt}


def _cubes(rows, edges=None) -> CubeSet:
    return CubeSet(
        session=None,
        transition=pd.DataFrame(edges) if edges is not None else None,
        quality=None, state_dict_version="sd_abc", services=["top"],
        requested_dates=["2026-07-27"], present_dates=["2026-07-27"],
        cond_transition=pd.DataFrame(rows),
    )


# 행동이 다음 화면을 **완전히** 결정한다: A는 항상 P, B는 항상 Q. 후보가 둘이라 log(2).
DETERMINES = [_row("X", "A", "P", 50), _row("X", "B", "Q", 50)]

# 행동이 아무것도 말해주지 않는다: 두 종류 모두 P·Q 반반. 0.
INDEPENDENT = [_row("X", "A", "P", 25), _row("X", "A", "Q", 25),
               _row("X", "B", "P", 25), _row("X", "B", "Q", 25)]


def test_one_row_per_from_kind_to():
    got = get_analysis("conditional_flow")(_cubes(DETERMINES))
    assert {"from_state", "action_kind", "to_state", "cnt",
            "share_of_origin"} <= set(got.frame.columns)
    assert len(got.frame) == 2


def test_the_share_is_within_the_from_state_and_kind():
    """분모는 (현재 화면, 행동) 이다 — "이 화면에서 이걸 눌렀을 때 어디로 가나"."""
    rows = [_row("X", "A", "P", 30), _row("X", "A", "Q", 10),
            _row("X", "B", "P", 100)]
    frame = get_analysis("conditional_flow")(_cubes(rows)).frame.set_index(
        ["from_state", "action_kind", "to_state"]
    )
    assert frame.loc[("X", "A", "P"), "share_of_origin"] == pytest.approx(0.75)
    assert frame.loc[("X", "A", "Q"), "share_of_origin"] == pytest.approx(0.25)
    assert frame.loc[("X", "B", "P"), "share_of_origin"] == pytest.approx(1.0)


def test_action_information_is_zero_when_the_action_says_nothing():
    got = get_analysis("conditional_flow")(_cubes(INDEPENDENT))
    assert got.headline["action_information"] == pytest.approx(0.0)


def test_action_information_is_log_two_when_the_action_decides_a_binary_choice():
    got = get_analysis("conditional_flow")(_cubes(DETERMINES))
    assert got.headline["action_information"] == pytest.approx(np.log(2))


def test_action_information_weights_kinds_by_volume_within_the_screen():
    """**대칭 픽스처로는 가중을 검증할 수 없다.** 90:10 으로 기울이면 갈린다.

    A(90건)는 P 로만 가고 B(10건)는 P·Q 반반이다.
    `H(다음|현재)` = H(0.95, 0.05) = 0.198515
    `H(다음|현재, 행동)` = 0.9·0 + 0.1·log2 = 0.069315   ← 물량 가중
    차이 = **0.129201**. 종류를 단순 평균하면 0.346574 가 되어 **음수**가 나온다.
    """
    rows = [_row("X", "A", "P", 90), _row("X", "B", "P", 5), _row("X", "B", "Q", 5)]
    got = get_analysis("conditional_flow")(_cubes(rows))
    assert got.headline["action_information"] == pytest.approx(0.129201, abs=1e-6)


def test_action_information_weights_screens_by_volume():
    """화면도 물량 가중이다. 작은 화면이 큰 화면과 같은 무게를 가지면 안 된다."""
    rows = DETERMINES + [_row("Y", "A", "P", 1), _row("Y", "A", "Q", 1)]
    got = get_analysis("conditional_flow")(_cubes(rows))
    # X(100건)는 log2, Y(2건)는 0 -> 가중 평균은 log2 에 아주 가깝다
    assert got.headline["action_information"] == pytest.approx(
        np.log(2) * 100 / 102, abs=1e-9
    )


def test_no_click_share_is_out_of_the_transition_count():
    """분모는 **전이 수**다. 이 큐브의 `cnt` 합은 (클릭, 전이) 쌍이라 전이 수가 아니다."""
    rows = DETERMINES + [_row("X", "(no_click)", "P", 40)]
    edges = [_edge("X", "P", 90), _edge("X", "Q", 50)]
    got = get_analysis("conditional_flow")(_cubes(rows, edges))
    assert got.headline["no_click_share"] == pytest.approx(40 / 140)


def test_no_click_share_is_nan_without_the_transition_cube():
    """전이 수를 모르면 NaN 이다. 이 큐브의 합으로 나누면 분모가 부푼 값이 나온다."""
    rows = DETERMINES + [_row("X", "(no_click)", "P", 40)]
    got = get_analysis("conditional_flow")(_cubes(rows))
    assert pd.isna(got.headline["no_click_share"])


def test_click_less_transitions_stay_in_the_frame():
    """빼면 "행동이 다음 화면을 결정한다" 가 행동 있는 전이만 본 결과가 된다."""
    rows = DETERMINES + [_row("X", "(no_click)", "P", 40)]
    got = get_analysis("conditional_flow")(_cubes(rows))
    assert "(no_click)" in set(got.frame["action_kind"])


def test_the_no_click_rows_are_excluded_from_action_information():
    """`(no_click)` 은 행동이 아니다. 행동 종류로 세면 "안 누름" 이 정보를 준 것처럼 된다."""
    with_none = DETERMINES + [_row("X", "(no_click)", "P", 40)]
    assert get_analysis("conditional_flow")(
        _cubes(with_none)
    ).headline["action_information"] == pytest.approx(np.log(2))


def test_a_cube_without_the_cond_transition_frame_is_refused():
    empty = CubeSet(session=None, transition=None, quality=None,
                    state_dict_version="sd_abc", services=["top"],
                    requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="needs the cond_transition cube"):
        get_analysis("conditional_flow")(empty)

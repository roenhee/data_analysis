"""서비스 간 이동. 화면 간 전이의 절반이 여기 있다."""
import numpy as np
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _cubes(rows) -> CubeSet:
    edges = pd.DataFrame([
        {**AXES, "from_state": f, "to_state": t, "cnt": c,
         "dur_sum": float(c) * 10.0, "dur_n": c}
        for f, t, c in rows
    ])
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd_abc", services=["top", "media"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


# 화면->화면 400건 중 100건이 서비스를 건너뛴다 -> cross_service_share = 0.25
ROWS = [("START", "top/a", 50), ("top/a", "top/b", 300),
        ("top/b", "media/x", 100), ("media/x", "EXIT", 50)]


def test_one_row_per_service_pair():
    """`media/x -> EXIT` 는 도착이 화면이 아니라 빠진다 — media 출발 쌍이 생기지 않는다."""
    got = get_analysis("cross_service_flow")(_cubes(ROWS))
    pairs = set(zip(got.frame["from_service"], got.frame["to_service"]))
    assert pairs == {("top", "top"), ("top", "media")}


def test_the_frame_keeps_the_counts_and_the_within_share():
    got = get_analysis("cross_service_flow")(_cubes(ROWS)).frame.set_index(
        ["from_service", "to_service"]
    )
    assert got.loc[("top", "top"), "cnt"] == pytest.approx(300.0)
    assert got.loc[("top", "media"), "cnt"] == pytest.approx(100.0)
    # top 에서 출발한 400건 중 media 로 간 것이 100건
    assert got.loc[("top", "media"), "share_of_origin"] == pytest.approx(0.25)


def test_start_and_exit_are_excluded_because_they_have_no_service():
    """세션 경계는 서비스 간 이동이 아니다. 넣으면 분모가 세션 수만큼 부푼다."""
    got = get_analysis("cross_service_flow")(_cubes(ROWS))
    assert not {"START", "EXIT"} & set(got.frame["from_service"])
    assert not {"START", "EXIT"} & set(got.frame["to_service"])


def test_headline_cross_service_share():
    got = get_analysis("cross_service_flow")(_cubes(ROWS))
    assert got.headline["cross_service_share"] == pytest.approx(0.25)


def test_headline_switch_entropy_is_zero_when_every_switch_goes_one_way():
    """건너뛰는 이동이 한 쌍뿐이면 엔트로피 0 이다."""
    got = get_analysis("cross_service_flow")(_cubes(ROWS))
    assert got.headline["switch_entropy"] == pytest.approx(0.0)


def test_headline_switch_entropy_is_log_two_for_two_equal_switches():
    """서로 다른 두 이동이 반반이면 log(2) 다."""
    rows = [("top/a", "media/x", 100), ("media/x", "top/a", 100),
            ("top/a", "top/b", 200)]
    got = get_analysis("cross_service_flow")(_cubes(rows))
    assert got.headline["switch_entropy"] == pytest.approx(np.log(2))
    assert got.headline["cross_service_share"] == pytest.approx(0.5)


def test_switch_entropy_is_volume_weighted_not_a_count_of_pairs():
    """**대칭 픽스처로는 가중을 검증할 수 없다** — 반반이면 어떤 가중이든 log(2) 다.

    75:25 로 기울이면 갈린다: 물량 가중은 0.562335, 쌍 개수 기준(균등)은 log(2)=0.693147.
    앞 계획서에서 같은 함정을 밟아 mutation check 가 반만 들었다.
    """
    rows = [("top/a", "media/x", 300), ("media/x", "top/a", 100),
            ("top/a", "top/b", 600)]
    got = get_analysis("cross_service_flow")(_cubes(rows))
    p = np.array([0.75, 0.25])
    assert got.headline["switch_entropy"] == pytest.approx(-(p * np.log(p)).sum())
    assert got.headline["switch_entropy"] == pytest.approx(0.562335, abs=1e-6)


def test_a_single_service_cube_reports_zero_crossing_not_nan():
    """한 서비스만 있으면 건너뛰는 이동이 0 이다 — "모른다" 가 아니라 "없다"."""
    rows = [("START", "top/a", 10), ("top/a", "top/b", 90), ("top/b", "EXIT", 10)]
    got = get_analysis("cross_service_flow")(_cubes(rows))
    assert got.headline["cross_service_share"] == pytest.approx(0.0)
    assert got.headline["switch_entropy"] == pytest.approx(0.0)


def test_a_cube_with_no_screen_transitions_raises():
    rows = [("START", "EXIT", 10)]
    with pytest.raises(ValueError, match="no screen-to-screen transitions"):
        get_analysis("cross_service_flow")(_cubes(rows))


def test_a_cube_whose_screens_only_exit_raises_instead_of_dividing_by_zero():
    """도착 서비스를 안 보고 자르면 여기서 `0/0` 이 된다.

    `groupby` 가 NaN 키를 버리므로 도착 필터는 보통 관측되지 않는다 — **이 경우만 다르다.**
    `top/a -> EXIT` 하나뿐이면 출발만 보면 프레임이 비지 않아 통과하고, 그다음 groupby 가
    그 행을 버려서 분모가 0 이 된다. 거부해야 하는 자리에서 `ZeroDivisionError` 가 난다.
    """
    rows = [("START", "top/a", 10), ("top/a", "EXIT", 10)]
    with pytest.raises(ValueError, match="no screen-to-screen transitions"):
        get_analysis("cross_service_flow")(_cubes(rows))

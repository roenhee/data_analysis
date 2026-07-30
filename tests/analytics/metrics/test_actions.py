"""화면 안의 클릭 분포. **화면 안에서 정규화하는 것**이 요점이다."""
import pandas as pd
import pytest

from analytics.metrics.actions import click_share, clicks_per_visit


def _actions() -> pd.DataFrame:
    return pd.DataFrame([
        {"screen": "top/홈탭_진입", "action_kind": "ClickContent",
         "layer1": "home_main", "layer2": "home_main>FEED", "cnt": 60},
        {"screen": "top/홈탭_진입", "action_kind": "(none)",
         "layer1": "home_main", "layer2": "home_main>SEARCH", "cnt": 40},
        # 트래픽이 적은 화면 — 전역 정규화하면 이 화면의 분포가 지워진다.
        {"screen": "media/뉴스", "action_kind": "ClickContent",
         "layer1": "m_news", "layer2": "other", "cnt": 2},
        {"screen": "media/뉴스", "action_kind": "Share",
         "layer1": "other", "layer2": "other", "cnt": 8},
    ])


def test_the_share_sums_to_one_within_each_screen():
    got = click_share(_actions(), by=("action_kind",))
    for _, group in got.groupby("screen"):
        assert group["share"].sum() == pytest.approx(1.0)


def test_the_share_is_per_screen_not_global():
    """전역 정규화하면 트래픽 많은 화면이 분포를 지배한다 — media 는 8/110 이 된다."""
    got = click_share(_actions(), by=("action_kind",)).set_index(
        ["screen", "action_kind"]
    )
    assert got.loc[("media/뉴스", "Share"), "share"] == pytest.approx(0.8)
    assert got.loc[("top/홈탭_진입", "ClickContent"), "share"] == pytest.approx(0.6)


def test_the_numerator_ships_with_the_ratio():
    """비율만 내면 소비자가 검산할 수 없다 — 이 층의 규칙이다."""
    got = click_share(_actions(), by=("action_kind",))
    assert {"cnt", "share"} <= set(got.columns)


def test_folding_layer2_into_layer1_preserves_the_total():
    """접기 규약 검증 — layer1 로 합친 값이 layer2 합계와 같아야 한다."""
    one = click_share(_actions(), by=("layer1",)).set_index(["screen", "layer1"])
    two = click_share(_actions(), by=("layer1", "layer2"))
    rolled = two.groupby(["screen", "layer1"])["cnt"].sum()
    for key, value in rolled.items():
        assert one.loc[key, "cnt"] == pytest.approx(value)


def test_the_other_bucket_is_reported_not_dropped():
    """`other` 를 빼면 비중의 분모가 줄어 남은 값이 부푼다."""
    got = click_share(_actions(), by=("layer1",))
    assert "other" in set(got["layer1"])
    assert got[got["screen"] == "media/뉴스"]["share"].sum() == pytest.approx(1.0)


def test_rows_are_sorted_by_volume_within_a_screen():
    got = click_share(_actions(), by=("action_kind",))
    for _, group in got.groupby("screen"):
        assert group["cnt"].is_monotonic_decreasing


def test_an_empty_frame_gives_an_empty_result_rather_than_raising():
    empty = pd.DataFrame(columns=["screen", "action_kind", "layer1", "layer2", "cnt"])
    assert click_share(empty, by=("action_kind",)).empty


def _edges() -> pd.DataFrame:
    """전이 큐브. `from_state` 가 `action` 큐브의 `screen` 과 **같은 값**이다."""
    return pd.DataFrame([
        {"from_state": "top/홈탭_진입", "to_state": "EXIT", "cnt": 50,
         "dur_sum": 500.0, "dur_n": 50},
        {"from_state": "media/뉴스", "to_state": "EXIT", "cnt": 5,
         "dur_sum": 50.0, "dur_n": 5},
    ])


def test_clicks_per_visit_joins_the_two_cubes_on_the_shared_screen_name():
    """Task 1 이 화면 식을 맞춘 값을 여기서 회수한다 — `common.page` 였으면 불가능하다."""
    got = clicks_per_visit(_actions(), _edges()).set_index("screen")
    assert got.loc["top/홈탭_진입", "clicks_per_visit"] == pytest.approx(100 / 50)
    assert got.loc["media/뉴스", "clicks_per_visit"] == pytest.approx(10 / 5)


def test_a_screen_with_no_visits_is_nan_not_infinity():
    """방문이 0 이면 "모른다" 다. `inf` 는 그럴듯한 거짓말이다."""
    got = clicks_per_visit(_actions(), _edges().iloc[:1]).set_index("screen")
    assert pd.isna(got.loc["media/뉴스", "clicks_per_visit"])


def test_start_clicks_have_no_visit_even_though_start_is_in_the_transition_cube():
    """**실큐브에서 `START` 는 from_state 로 3억 8,276만 건 있다.** 그건 세션 수다.

    그대로 나누면 "세션 시작 시점의 방문당 클릭" 이라는 없는 값이 그럴듯하게 나온다.
    첫 화면 이전 클릭이 `action` 큐브에서 `START` 에 붙으므로 그 행은 실제로 생긴다 —
    `START` 없는 픽스처로 테스트하면 이 결함을 못 본다(처음 그렇게 썼다).
    """
    actions = pd.concat([_actions(), pd.DataFrame([
        {"screen": "START", "action_kind": "AppLaunch", "layer1": "other",
         "layer2": "other", "cnt": 7},
    ])], ignore_index=True)
    edges = pd.concat([_edges(), pd.DataFrame([
        {"from_state": "START", "to_state": "top/홈탭_진입", "cnt": 1000,
         "dur_sum": 0.0, "dur_n": 0},
    ])], ignore_index=True)
    got = clicks_per_visit(actions, edges).set_index("screen")
    assert got.loc["START", "cnt"] == 7
    assert pd.isna(got.loc["START", "clicks_per_visit"])
    # 화면 쪽 값은 `START` 엣지가 있어도 그대로다.
    assert got.loc["top/홈탭_진입", "clicks_per_visit"] == pytest.approx(100 / 50)


def test_a_screen_with_zero_visits_is_nan_not_infinity():
    """전이 큐브의 `cnt` 는 `count(*)` 라 0 이 될 수 없지만, 이 함수는 프레임을 받는다.

    미리 걸러진 프레임이 0 합계를 넘길 수 있고 그때 `inf` 가 나오면 그럴듯한 거짓말이다.
    순수 함수의 계약은 큐브가 아니라 **입력 전체**다.
    """
    edges = pd.DataFrame([
        {"from_state": "top/홈탭_진입", "to_state": "EXIT", "cnt": 0,
         "dur_sum": 0.0, "dur_n": 0},
    ])
    got = clicks_per_visit(_actions(), edges).set_index("screen")
    assert got.loc["top/홈탭_진입", "visits"] == 0
    assert pd.isna(got.loc["top/홈탭_진입", "clicks_per_visit"])


def test_the_visit_count_ships_with_the_ratio():
    got = clicks_per_visit(_actions(), _edges())
    assert {"cnt", "visits", "clicks_per_visit"} <= set(got.columns)

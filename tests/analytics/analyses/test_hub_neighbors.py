"""허브 이웃 분석. 한 화면으로 들어오는(IN) · 나가는(OUT) 이웃을 건수·비중으로 본다."""
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

# 손으로 푼 체인. 허브 후보 A 는 들어오는 길이 셋(START·B·C), 나가는 길이 둘(B·EXIT)이라
# IN·OUT 을 손으로 검산할 수 있다.
#   START->A(100), A->B(60), A->EXIT(40), B->A(30), B->EXIT(30), C->A(10)
# A 의 OUT: B(60)/EXIT(40) — 합 100.  A 의 IN: START(100)/B(30)/C(10) — 합 140.
CHAIN = [
    ("START", "A", 100), ("A", "B", 60), ("A", "EXIT", 40),
    ("B", "A", 30), ("B", "EXIT", 30), ("C", "A", 10),
]


def _edges(rows) -> pd.DataFrame:
    return pd.DataFrame([
        {"period": "2026-07-27", "from_state": f, "to_state": t, "cnt": c,
         "dur_n": c, "dur_sum": float(c) * 10.0}
        for f, t, c in rows
    ])


def _cubes(rows=CHAIN) -> CubeSet:
    return CubeSet(session=None, transition=_edges(rows), quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def test_out_shares_sum_to_one_for_the_hub():
    got = get_analysis("hub_neighbors")(_cubes(), screen="A").frame
    out = got[got["direction"] == "OUT"]
    assert out["share"].sum() == pytest.approx(1.0)


def test_in_shares_sum_to_one_for_the_hub():
    got = get_analysis("hub_neighbors")(_cubes(), screen="A").frame
    inn = got[got["direction"] == "IN"]
    assert inn["share"].sum() == pytest.approx(1.0)


def test_out_neighbors_match_the_hand_solved_chain():
    got = get_analysis("hub_neighbors")(_cubes(), screen="A").frame.set_index(
        ["direction", "neighbor"])
    assert got.loc[("OUT", "B"), "cnt"] == pytest.approx(60.0)
    assert got.loc[("OUT", "B"), "share"] == pytest.approx(0.6)
    assert got.loc[("OUT", "EXIT"), "cnt"] == pytest.approx(40.0)
    assert got.loc[("OUT", "EXIT"), "share"] == pytest.approx(0.4)


def test_in_neighbors_match_the_hand_solved_chain():
    got = get_analysis("hub_neighbors")(_cubes(), screen="A").frame.set_index(
        ["direction", "neighbor"])
    assert got.loc[("IN", "START"), "cnt"] == pytest.approx(100.0)
    assert got.loc[("IN", "B"), "cnt"] == pytest.approx(30.0)
    assert got.loc[("IN", "C"), "cnt"] == pytest.approx(10.0)
    assert got.loc[("IN", "START"), "share"] == pytest.approx(100 / 140)


def test_explicit_screen_returns_neighbors_for_that_screen_only():
    """hub 열이 요청한 화면 하나로만 채워진다(다른 화면이 섞이지 않는다)."""
    got = get_analysis("hub_neighbors")(_cubes(), screen="B").frame
    assert set(got["hub"]) == {"B"}


def test_empty_screen_auto_picks_a_real_screen_not_start_or_exit():
    got = get_analysis("hub_neighbors")(_cubes())
    hub = got.frame["hub"].iloc[0]
    assert hub not in ("START", "EXIT")
    assert hub in {"A", "B", "C"}


def test_headline_degrees_match_the_fixture_for_the_explicit_hub():
    got = get_analysis("hub_neighbors")(_cubes(), screen="A")
    assert got.headline["in_degree"] == pytest.approx(3.0)
    assert got.headline["out_degree"] == pytest.approx(2.0)


def test_in_top_share_and_out_top_share_are_at_most_one():
    got = get_analysis("hub_neighbors")(_cubes(), screen="A")
    assert got.headline["in_top_share"] <= 1.0
    assert got.headline["out_top_share"] <= 1.0


def test_unknown_screen_raises_value_error():
    with pytest.raises(ValueError, match="unknown screen"):
        get_analysis("hub_neighbors")(_cubes(), screen="nope")


def test_a_missing_transition_cube_raises():
    missing = CubeSet(session=None, transition=None, quality=None,
                      state_dict_version="sd_abc", services=["top"],
                      requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="needs the transition cube"):
        get_analysis("hub_neighbors")(missing)


def test_viz_is_a_table_so_the_dashboard_draws_no_chart():
    """IN/OUT 를 한 막대에 섞으면 헷갈리므로 표만 그린다 — direction 열로 구분한다."""
    got = get_analysis("hub_neighbors")(_cubes(), screen="A")
    assert got.viz == {"kind": "table"}

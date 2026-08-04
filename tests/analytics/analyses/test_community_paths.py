"""군집별 대표 5-gram 경로. 노트북 `*_comm_top5.csv` 재현.

`screen_communities` 로 상태→군집을 얻고(전이 큐브), path 큐브 n=5 경로 중 다섯 상태가
모두 같은 군집인 것만 남겨 군집별 순위를 매긴다. 두 재료 다 필요하므로 CubeSet 은
전이 프레임과 경로 프레임을 함께 들고 있어야 한다.
"""
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis
from analytics.metrics.paths import OTHER_PATH

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")

# 삼각형 둘(test_communities.py 의 TWO_TRIANGLES 와 같은 모양). START/EXIT 는 군집
# 그래프에서 빠지므로 군집은 {A,B,C} 와 {X,Y,Z} 로 갈린다 — 가중치가 같아 동점이고,
# 동점은 min(그룹) 이름순이라 군집 0 = {A,B,C}, 군집 1 = {X,Y,Z} 다.
TWO_TRIANGLES = [
    ("START", "A", 10), ("START", "X", 10),
    ("A", "B", 10), ("B", "C", 10), ("C", "A", 10),
    ("X", "Y", 10), ("Y", "Z", 10), ("Z", "X", 10),
    ("C", "EXIT", 10), ("Z", "EXIT", 10),
]


def _edges(rows=TWO_TRIANGLES) -> pd.DataFrame:
    return pd.DataFrame([
        {"period": "2026-07-27", "from_state": f, "to_state": t, "cnt": c,
         "dur_n": c, "dur_sum": float(c) * 10.0}
        for f, t, c in rows
    ])


def _gram(path: str, cnt: int, dropped: int = 0) -> dict:
    return {**AXES, "n": 5, "path": path, "cnt": cnt, "distinct_dropped": dropped}


# 군집0(A,B,C) 안에 5-gram 둘(50, 30), 군집1(X,Y,Z) 안에 하나(40), 군집을 넘나드는 것
# 하나(가장 큰 999 인데도 빠져야 한다), 다섯 상태 모두 군집이 없는 것(미상 화면 Q) 하나,
# 그리고 `(other)` 컷 행 하나(경로가 아니라 컷의 크기).
GRAMS = [
    _gram("A>B>C>A>B", 50),
    _gram("B>C>A>B>C", 30),
    _gram("X>Y>Z>X>Y", 40),
    _gram("A>B>C>X>Y", 999),
    _gram("Q>Q>Q>Q>Q", 20),
    {**AXES, "n": 5, "path": OTHER_PATH, "cnt": 500, "distinct_dropped": 1000},
]


def _cubes(grams=GRAMS, edges_rows=TWO_TRIANGLES) -> CubeSet:
    return CubeSet(
        session=None, transition=_edges(edges_rows), quality=None,
        state_dict_version="sd_abc", services=["top"],
        requested_dates=["2026-07-27"], present_dates=["2026-07-27"],
        path=pd.DataFrame(grams),
    )


def test_a_cube_without_the_path_frame_is_refused():
    no_path = CubeSet(session=None, transition=_edges(), quality=None,
                      state_dict_version="sd_abc", services=["top"],
                      requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="needs the path cube"):
        get_analysis("community_paths")(no_path)


def test_a_cube_without_the_transition_frame_is_refused():
    no_edges = CubeSet(session=None, transition=None, quality=None,
                       state_dict_version="sd_abc", services=["top"],
                       requested_dates=["2026-07-27"], present_dates=["2026-07-27"],
                       path=pd.DataFrame(GRAMS))
    with pytest.raises(ValueError, match="needs the transition cube"):
        get_analysis("community_paths")(no_edges)


def test_cross_community_and_unknown_5grams_are_dropped():
    """군집을 넘나드는 경로(가장 물량이 크다)와, 다섯 상태 모두 군집이 없는 경로는
    대표 경로가 아니다."""
    got = get_analysis("community_paths")(_cubes())
    paths = set(got.frame["path"])
    assert "A>B>C>X>Y" not in paths
    assert "Q>Q>Q>Q>Q" not in paths
    assert OTHER_PATH not in paths


def test_kept_paths_are_ranked_per_community_starting_at_one():
    got = get_analysis("community_paths")(_cubes())
    assert got.frame["community"].nunique() == 2

    by_comm = {c: g.sort_values("rank") for c, g in got.frame.groupby("community")}
    for group in by_comm.values():
        assert group["rank"].tolist() == list(range(1, len(group) + 1))

    by_path = got.frame.set_index("path")
    # 군집0(A,B,C) 안에서는 cnt 50 짜리가 30 짜리보다 앞서야 한다(1위).
    assert by_path.loc["A>B>C>A>B", "community"] == by_path.loc["B>C>A>B>C", "community"]
    assert by_path.loc["A>B>C>A>B", "rank"] == 1
    assert by_path.loc["B>C>A>B>C", "rank"] == 2
    # 군집1(X,Y,Z) 안에는 하나뿐이라 1위다.
    assert by_path.loc["X>Y>Z>X>Y", "rank"] == 1


def test_support_in_comm_sums_to_one_within_each_community():
    got = get_analysis("community_paths")(_cubes())
    sums = got.frame.groupby("community")["support_in_comm"].sum()
    assert (sums.round(9) == 1.0).all()

    by_path = got.frame.set_index("path")
    assert by_path.loc["A>B>C>A>B", "support_in_comm"] == pytest.approx(50 / 80)
    assert by_path.loc["B>C>A>B>C", "support_in_comm"] == pytest.approx(30 / 80)
    assert by_path.loc["X>Y>Z>X>Y", "support_in_comm"] == pytest.approx(1.0)


def test_top_per_community_limits_rows_kept():
    got = get_analysis("community_paths")(_cubes(), top_per_community=1)
    counts = got.frame.groupby("community").size()
    assert (counts == 1).all()
    assert "B>C>A>B>C" not in set(got.frame["path"]), "2위는 top_per_community=1 이면 빠진다"


def test_headline_carries_coverage_metrics():
    got = get_analysis("community_paths")(_cubes())
    assert got.headline["communities_covered"] == pytest.approx(2.0)
    # A>B>C>A>B, B>C>A>B>C, X>Y>Z>X>Y 셋만 한 군집 안이다(컷 전, top_per_community 전).
    assert got.headline["within_community_5grams"] == pytest.approx(3.0)
    assert got.headline["top_support"] == pytest.approx(1.0)


def test_a_community_with_no_surviving_5grams_is_not_counted():
    """군집1(X,Y,Z) 은 존재해도 그 안 5-gram 이 하나도 안 남으면 커버리지에서 빠진다."""
    grams = [_gram("A>B>C>A>B", 50), _gram("B>C>A>B>C", 30)]
    got = get_analysis("community_paths")(_cubes(grams=grams))
    assert got.headline["communities_covered"] == pytest.approx(1.0)
    assert got.frame["community"].nunique() == 1


def test_viz_is_table_only():
    """경로 문자열이 길어 차트가 아니라 표만 낸다."""
    got = get_analysis("community_paths")(_cubes())
    assert got.viz == {"kind": "table"}


def test_frame_has_the_expected_columns_in_order():
    got = get_analysis("community_paths")(_cubes())
    assert list(got.frame.columns) == [
        "community", "rank", "path", "cnt", "support_in_comm"]

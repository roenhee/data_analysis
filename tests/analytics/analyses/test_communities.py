import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

# 삼각형 둘. START/EXIT 를 빼지 않으면 둘이 START 를 거쳐 이어져 한 덩어리가 된다.
TWO_TRIANGLES = [
    ("START", "A", 10), ("START", "X", 10),
    ("A", "B", 10), ("B", "C", 10), ("C", "A", 10),
    ("X", "Y", 10), ("Y", "Z", 10), ("Z", "X", 10),
    ("C", "EXIT", 10), ("Z", "EXIT", 10),
]

ONE_CLIQUE = [
    ("START", "A", 10),
    ("A", "B", 10), ("B", "C", 10), ("C", "A", 10), ("A", "C", 10),
    ("C", "EXIT", 10),
]


def _cubes(rows) -> CubeSet:
    edges = pd.DataFrame([
        {"period": "2026-07-27", "from_state": f, "to_state": t, "cnt": c,
         "dur_n": c, "dur_sum": float(c) * 10.0}
        for f, t, c in rows
    ])
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def test_two_disconnected_clusters_are_found_as_two_communities():
    got = get_analysis("screen_communities")(_cubes(TWO_TRIANGLES))
    assert got.frame["community"].nunique() == 2
    members = got.frame.groupby("community")["state"].apply(set).tolist()
    assert {"A", "B", "C"} in members
    assert {"X", "Y", "Z"} in members


def test_a_single_clique_is_one_community():
    got = get_analysis("screen_communities")(_cubes(ONE_CLIQUE))
    assert got.frame["community"].nunique() == 1


def test_every_screen_lands_in_exactly_one_community():
    got = get_analysis("screen_communities")(_cubes(TWO_TRIANGLES))
    assert got.frame["state"].tolist() == sorted(got.frame["state"])
    assert not got.frame["state"].duplicated().any()
    assert set(got.frame["state"]) == {"A", "B", "C", "X", "Y", "Z"}


def test_start_and_exit_are_excluded_from_communities():
    """START/EXIT 는 모든 화면과 이어져 군집을 뭉갠다."""
    got = get_analysis("screen_communities")(_cubes(TWO_TRIANGLES))
    assert "START" not in set(got.frame["state"])
    assert "EXIT" not in set(got.frame["state"])


def test_the_result_is_deterministic_for_a_fixed_seed():
    """Louvain 은 무작위 초기화가 있다. 시드를 고정하지 않으면 실행마다 답이 바뀐다."""
    first = get_analysis("screen_communities")(_cubes(TWO_TRIANGLES)).frame
    second = get_analysis("screen_communities")(_cubes(TWO_TRIANGLES)).frame
    assert first["community"].tolist() == second["community"].tolist()


def test_community_ids_are_assigned_by_descending_weight():
    """0번은 항상 가장 큰 군집이다. 번호가 뜻을 가져야 세그먼트끼리 견줄 수 있다."""
    rows = TWO_TRIANGLES + [("X", "Y", 500), ("Y", "Z", 500)]
    got = get_analysis("screen_communities")(_cubes(rows))
    biggest = got.frame[got.frame["community"] == 0]
    assert set(biggest["state"]) == {"X", "Y", "Z"}


def test_community_ids_do_not_move_when_the_cube_rows_are_reordered():
    """시드만 고정해선 부족하다 — 군집 **번호**도 안정해야 발행물이 재현된다.

    Louvain 이 돌려주는 순서는 그래프 노드 순서를 따르고, 노드 순서는 엣지 행 순서를
    따른다. 두 클러스터의 행 순서만 맞바꾸면 원시 순서가 뒤집히는 것을 확인했다 —
    읽는 날짜 범위나 parquet 파일 순서가 달라지면 실제로 일어나는 일이다.
    """
    swapped = TWO_TRIANGLES[5:] + TWO_TRIANGLES[:5]
    first = get_analysis("screen_communities")(_cubes(TWO_TRIANGLES)).frame
    second = get_analysis("screen_communities")(_cubes(swapped)).frame
    assert first.set_index("state")["community"].to_dict() == (
        second.set_index("state")["community"].to_dict()
    )


def test_headline_carries_the_community_count_and_modularity():
    got = get_analysis("screen_communities")(_cubes(TWO_TRIANGLES))
    assert got.headline["communities"] == 2
    # 무게가 같은 삼각형 둘이면 Q = 1 - 2*(1/2)^2 = 0.5 (손계산)
    assert got.headline["modularity"] == pytest.approx(0.5)


def test_a_chain_with_no_screen_to_screen_edge_is_refused():
    """화면끼리 이어진 엣지가 없으면 군집이라는 말 자체가 성립하지 않는다."""
    lonely = _cubes([("START", "A", 10), ("A", "EXIT", 10)])
    with pytest.raises(ValueError, match="no screen-to-screen"):
        get_analysis("screen_communities")(lonely)

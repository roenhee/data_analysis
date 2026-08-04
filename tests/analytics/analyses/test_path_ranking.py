"""경로 순위 분석. 컷의 크기를 headline 에 싣는 것이 요점이다."""
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis
from analytics.metrics.paths import OTHER_PATH

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _row(n: int, path: str, cnt: int, dropped: int = 0) -> dict:
    return {**AXES, "n": n, "path": path, "cnt": cnt, "distinct_dropped": dropped}


# n=3: a>b>c 50, a>b>d 30, 잘린 꼬리 20(종수 400). 커버리지 0.8
# n=4: 하나 10 에 꼬리 90(종수 9000) — 꼬리가 지배한다
ROWS = [
    _row(3, "top/a>top/b>top/c", 50),
    _row(3, "top/a>top/b>top/d", 30),
    _row(3, OTHER_PATH, 20, 400),
    _row(4, "top/a>top/b>top/c>top/d", 10),
    _row(4, OTHER_PATH, 90, 9000),
]


def _cubes(rows=ROWS) -> CubeSet:
    return CubeSet(
        session=None, transition=None, quality=None,
        state_dict_version="sd_abc", services=["top"],
        requested_dates=["2026-07-27"], present_dates=["2026-07-27"],
        path=pd.DataFrame(rows),
    )


def test_n_is_required_because_the_populations_differ():
    """n=3 과 n=4 를 합치면 같은 방문이 여러 번 세어진다. 기본값을 주지 않는다."""
    with pytest.raises(TypeError):
        get_analysis("path_ranking")(_cubes())


def test_one_row_per_kept_path():
    got = get_analysis("path_ranking")(_cubes(), n=3)
    assert got.frame["path"].tolist() == [
        "top/a>top/b>top/c", "top/a>top/b>top/d"
    ]
    assert {"path", "cnt", "share"} <= set(got.frame.columns)


def test_the_other_row_is_not_a_path():
    """실측 n=4 는 `(other)` 가 90 대 10 이라 순위에 남기면 1위가 된다."""
    assert OTHER_PATH not in set(get_analysis("path_ranking")(_cubes(), n=4)
                                 .frame["path"])


def test_the_share_denominator_includes_the_cut_tail():
    """상위 안에서만 정규화하면 남은 값이 부푼다."""
    got = get_analysis("path_ranking")(_cubes(), n=3).frame.set_index("path")
    assert got.loc["top/a>top/b>top/c", "share"] == pytest.approx(0.5)


def test_headline_carries_the_size_of_the_cut():
    """커버리지 0.1 이 "200개가 꼬리 전부" 인지 "9,000개를 잘랐" 는지로 해석이 갈린다."""
    got = get_analysis("path_ranking")(_cubes(), n=4)
    assert got.headline["coverage"] == pytest.approx(0.1)
    assert got.headline["distinct_dropped"] == pytest.approx(9000.0)
    assert got.headline["paths"] == pytest.approx(1.0)


def test_headline_top_path_share_is_the_leader():
    got = get_analysis("path_ranking")(_cubes(), n=3)
    assert got.headline["top_path_share"] == pytest.approx(0.5)


def test_headline_n_is_carried_so_a_comparison_cannot_mix_them():
    """`compare` 가 headline 델타를 내므로 n 이 거기 있어야 섞인 걸 알아챌 수 있다."""
    assert get_analysis("path_ranking")(_cubes(), n=3).headline["n"] == 3.0
    assert get_analysis("path_ranking")(_cubes(), n=4).headline["n"] == 4.0


def test_a_dominant_tail_is_warned_about():
    """`(other)` 가 절반을 넘으면 상위 200 이 대표성을 잃는다."""
    got = get_analysis("path_ranking")(_cubes(), n=4)
    assert "path_tail_dominates" in [w["check_name"] for w in got.envelope["warnings"]]
    clean = get_analysis("path_ranking")(_cubes(), n=3)
    assert "path_tail_dominates" not in [
        w["check_name"] for w in clean.envelope["warnings"]
    ]


def test_a_missing_n_raises_rather_than_returning_empty():
    with pytest.raises(KeyError, match="no rows for n"):
        get_analysis("path_ranking")(_cubes(), n=5)


def test_a_cube_without_the_path_frame_is_refused():
    empty = CubeSet(session=None, transition=None, quality=None,
                    state_dict_version="sd_abc", services=["top"],
                    requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="needs the path cube"):
        get_analysis("path_ranking")(empty, n=3)


def test_segment_split_rows_for_one_path_are_summed_before_ranking():
    """path 큐브는 세그먼트(축 조합)별로 쪼개져 있다 — 같은 경로가 os·성별·버전마다 다른
    행이다. 합쳐서 순위를 매기지 않으면 조각 하나가 순위·비중이 되어 전부 틀린다
    (실데이터에서 paths 가 고유 경로 1,856 이 아니라 조각 36만 개로 나왔다).

    c 를 두 조각(30+20=50)으로, d 를 단일 40 으로 둔다. 합치면 c(50)>d(40) 라 c 가 1위이고
    경로는 2 개다. 합치지 않으면 최대 조각이 d=40 이라 순위가 뒤집힌다.
    """
    rows = [_row(3, "top/a>top/b>top/c", 30), _row(3, "top/a>top/b>top/c", 20),
            _row(3, "top/a>top/b>top/d", 40)]
    got = get_analysis("path_ranking")(_cubes(rows), n=3)
    assert got.frame["path"].tolist() == ["top/a>top/b>top/c", "top/a>top/b>top/d"]
    assert got.headline["paths"] == 2.0
    by_path = got.frame.set_index("path")
    assert by_path.loc["top/a>top/b>top/c", "cnt"] == 50.0
    # 비중 분모는 컷 이전 전체(50+40=90) — 조각 합이 아니다.
    assert by_path.loc["top/a>top/b>top/c", "share"] == pytest.approx(50 / 90)

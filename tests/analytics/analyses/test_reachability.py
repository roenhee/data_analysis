import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

# A 는 30% 로 T 로 직행하고 70% 로 B 를 거쳐 T 에 닿는다.
#   1걸음 안에 0.3, 2걸음 안에 0.3 + 0.7 = 1.0
BRANCHED = [("START", "A", 10, 0), ("A", "T", 3, 2), ("A", "B", 7, 5),
            ("B", "T", 7, 5), ("T", "EXIT", 10, 8)]

# 오직 두 걸음짜리 경로. 1걸음 안에 0, 2걸음 안에 1.0
TWO_STEP = [("START", "A", 10, 0), ("A", "B", 10, 7), ("B", "T", 10, 7),
            ("T", "EXIT", 10, 8)]


def _cubes(rows) -> CubeSet:
    edges = pd.DataFrame([
        {"period": "2026-07-27", "from_state": f, "to_state": t, "cnt": c,
         "dur_n": n, "dur_sum": float(n) * 10.0}
        for f, t, c, n in rows
    ])
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def _curve(rows, **params):
    got = get_analysis("reachability")(_cubes(rows), **params)
    return got, got.frame.set_index("k")["p_hit_within"]


def test_direct_edge_is_reached_in_one_step_with_its_probability():
    _, curve = _curve(BRANCHED, source="A", target="T", max_k=3)
    assert curve[1] == pytest.approx(0.3)


def test_two_step_path_needs_two_steps():
    _, curve = _curve(TWO_STEP, source="A", target="T", max_k=3)
    assert curve[1] == pytest.approx(0.0)
    assert curve[2] == pytest.approx(1.0)


def test_probability_is_monotonically_non_decreasing_in_k():
    """목표를 흡수 상태로 바꾸지 않으면 지나쳐 간 확률이 빠져 곡선이 내려간다."""
    _, curve = _curve(BRANCHED, source="A", target="T", max_k=6)
    values = curve.tolist()
    assert all(b >= a for a, b in zip(values, values[1:]))
    assert values[-1] == pytest.approx(1.0)


def test_a_target_passed_through_is_still_counted_after_it_is_left():
    """T 에서 다시 나가는 체인. "k 걸음 안에 닿았다" 는 머무는 것과 무관하다."""
    passing = [("START", "A", 10, 0), ("A", "T", 10, 7), ("T", "B", 10, 7),
               ("B", "EXIT", 10, 8)]
    _, curve = _curve(passing, source="A", target="T", max_k=4)
    assert curve[1] == pytest.approx(1.0)
    assert curve[4] == pytest.approx(1.0)


def test_an_unreachable_target_stays_at_zero():
    apart = BRANCHED + [("X", "Z", 5, 3), ("Z", "EXIT", 5, 3)]
    _, curve = _curve(apart, source="A", target="Z", max_k=5)
    assert (curve == 0.0).all()


def test_the_source_state_must_exist():
    with pytest.raises(KeyError, match="NOPE"):
        _curve(BRANCHED, source="NOPE", target="T", max_k=3)


def test_the_target_state_must_exist():
    with pytest.raises(KeyError, match="NOPE"):
        _curve(BRANCHED, source="A", target="NOPE", max_k=3)


def test_headline_carries_p_hit_within_the_max_k():
    got, _ = _curve(BRANCHED, source="A", target="T", max_k=3)
    assert got.headline["p_hit_within_3"] == pytest.approx(1.0)


def test_the_frame_records_which_pair_it_is_about():
    """발행물이 스스로를 설명해야 한다 — 어느 쌍의 곡선인지 프레임에 남긴다."""
    got, _ = _curve(BRANCHED, source="A", target="T", max_k=2)
    assert set(got.frame["source"]) == {"A"}
    assert set(got.frame["target"]) == {"T"}

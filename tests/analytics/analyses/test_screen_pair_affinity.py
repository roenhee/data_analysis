"""PMI 쌍 분석. headline 이 상호정보량인 것이 요점이다."""
import numpy as np
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis


def _cubes(rows) -> CubeSet:
    edges = pd.DataFrame([
        {"period": "2026-07-27", "from_state": f, "to_state": t, "cnt": c,
         "dur_n": c, "dur_sum": float(c) * 10.0}
        for f, t, c in rows
    ])
    return CubeSet(session=None, transition=edges, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


# 완전 결정적인 짝짓기: A는 항상 X로, B는 항상 Y로 간다.
# 그러면 현재 화면이 다음 화면을 완전히 결정하므로 상호정보량 = log(2) 다.
PAIRED = [("A", "X", 50), ("B", "Y", 50)]

# 완전 독립: A·B 가 각각 X·Y 로 반반 간다. 상호정보량 = 0.
INDEPENDENT = [("A", "X", 25), ("A", "Y", 25), ("B", "X", 25), ("B", "Y", 25)]


def test_one_row_per_observed_pair():
    got = get_analysis("screen_pair_affinity")(_cubes(PAIRED))
    assert len(got.frame) == 2
    assert {"from_state", "to_state", "cnt", "pmi"} <= set(got.frame.columns)


def test_the_rows_are_sorted_by_affinity():
    rows = [("A", "X", 50), ("A", "Y", 50), ("B", "Y", 1)]
    got = get_analysis("screen_pair_affinity")(_cubes(rows))
    assert got.frame["pmi"].is_monotonic_decreasing


def test_headline_mutual_information_is_zero_when_the_next_screen_is_independent():
    got = get_analysis("screen_pair_affinity")(_cubes(INDEPENDENT))
    assert got.headline["mutual_information"] == pytest.approx(0.0)


def test_headline_mutual_information_is_log_two_for_a_perfect_pairing():
    """현재 화면이 다음 화면을 완전히 결정하고 후보가 둘이면 log(2) 다."""
    got = get_analysis("screen_pair_affinity")(_cubes(PAIRED))
    assert got.headline["mutual_information"] == pytest.approx(np.log(2))


def test_a_lopsided_perfect_pairing_gives_the_entropy_of_the_current_screen():
    """결정적 짝짓기의 상호정보량은 현재 화면 분포의 엔트로피다.

    후보가 반반인 `PAIRED` 로는 **가중을 검증할 수 없다** — 두 쌍의 `cnt` 가 같아서 물량
    가중과 단순 평균이 똑같이 log(2) 를 낸다. 90:10 으로 기울이면 갈린다: 가중은
    0.325083(= H(0.9, 0.1)), 단순 평균은 1.203973 이다. 계획서가 적어 둔 mutation check
    가 반만 들은 이유가 이것이고, 그래서 이 픽스처를 함께 둔다.
    """
    got = get_analysis("screen_pair_affinity")(_cubes([("A", "X", 90), ("B", "Y", 10)]))
    p = np.array([0.9, 0.1])
    assert got.headline["mutual_information"] == pytest.approx(-(p * np.log(p)).sum())
    assert got.headline["mutual_information"] == pytest.approx(0.325083, abs=1e-6)


def test_headline_is_the_cnt_weighted_mean_of_pmi():
    """상호정보량 = Σ p(i,j)·PMI(i,j). 단순 평균이 아니라 물량 가중이다."""
    rows = [("A", "X", 90), ("A", "Y", 10), ("B", "Y", 100)]
    got = get_analysis("screen_pair_affinity")(_cubes(rows))
    weights = got.frame["cnt"] / got.frame["cnt"].sum()
    assert got.headline["mutual_information"] == pytest.approx(
        float((got.frame["pmi"] * weights).sum())
    )
    assert got.headline["pairs"] == 3


def test_thin_cells_are_flagged_because_their_pmi_spikes_hardest():
    rows = PAIRED + [("A", "Z", 1)]
    got = get_analysis("screen_pair_affinity")(_cubes(rows))
    assert [w["check_name"] for w in got.envelope["warnings"]] == [
        "thin_transition_cells"
    ]


def test_an_empty_transition_frame_raises_rather_than_returning_zeros():
    empty = CubeSet(session=None, transition=pd.DataFrame(
        columns=["period", "from_state", "to_state", "cnt", "dur_n", "dur_sum"]),
        quality=None, state_dict_version="sd_abc", services=["top"],
        requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="no transitions"):
        get_analysis("screen_pair_affinity")(empty)

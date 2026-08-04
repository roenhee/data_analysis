"""1차 마르코프 가정 검정. **관측 3-gram을 1차 예측과 대조한다.**

전이 큐브 하나만 보면 "다음 화면은 현재 화면만으로 정해진다" 는 가정이 검증되지 않는다 —
그 큐브 자체가 그 가정으로 만들어졌기 때문이다. `path` 큐브의 3-gram 이 있어야 "직전
화면을 하나 더 알면 예측이 나아지는가" 를 물을 수 있다.
"""
import numpy as np
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis
from analytics.metrics.paths import OTHER_PATH

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _gram(a: str, b: str, c: str, cnt: int) -> dict:
    return {**AXES, "n": 3, "path": f"{a}>{b}>{c}", "cnt": cnt,
            "distinct_dropped": 0}


def _edge(f: str, t: str, cnt: int) -> dict:
    return {**AXES, "from_state": f, "to_state": t, "cnt": cnt,
            "dur_sum": float(cnt) * 10.0, "dur_n": cnt}


def _cubes(grams, edges) -> CubeSet:
    return CubeSet(
        session=None, transition=pd.DataFrame(edges), quality=None,
        state_dict_version="sd_abc", services=["top"],
        requested_dates=["2026-07-27"], present_dates=["2026-07-27"],
        path=pd.DataFrame(grams),
    )


# 1차가 완벽히 맞는 경우: B 다음은 항상 C. 직전이 A든 X든 상관없다.
FIRST_ORDER = (
    [_gram("A", "B", "C", 50), _gram("X", "B", "C", 50)],
    [_edge("B", "C", 100)],
)

# 1차가 틀리는 경우: B 다음이 직전 화면에 **완전히** 달렸다.
#   A>B 다음은 항상 C, X>B 다음은 항상 D.
# 1차 예측은 C·D 반반이므로 초과 정보량 = log(2).
SECOND_ORDER = (
    [_gram("A", "B", "C", 50), _gram("X", "B", "D", 50)],
    [_edge("B", "C", 50), _edge("B", "D", 50)],
)


def test_excess_information_is_zero_when_first_order_holds():
    """직전 화면이 아무것도 더 말해주지 않으면 0 이다."""
    got = get_analysis("markov_order_test")(_cubes(*FIRST_ORDER))
    assert got.headline["excess_information"] == pytest.approx(0.0)


def test_excess_information_is_log_two_when_history_decides_a_binary_choice():
    """직전 화면이 다음을 완전히 결정하고 후보가 둘이면 log(2) 다."""
    got = get_analysis("markov_order_test")(_cubes(*SECOND_ORDER))
    assert got.headline["excess_information"] == pytest.approx(np.log(2))


def test_excess_information_weights_contexts_by_volume():
    """**대칭 픽스처로는 가중을 검증할 수 없다.** 90:10 으로 기울인다.

    A>B(90건)는 C 로만, X>B(10건)는 C·D 반반. 1차 예측은 C 95 / D 5 다.
    KL 가중합 = 0.9·KL(C만 ‖ 0.95/0.05) + 0.1·KL(반반 ‖ 0.95/0.05)
              = 0.9·0.051293 + 0.1·0.830366 = **0.129201**
    문맥을 단순 평균하면 0.440830 으로 3.4배가 된다.
    """
    grams = [_gram("A", "B", "C", 90), _gram("X", "B", "C", 5),
             _gram("X", "B", "D", 5)]
    edges = [_edge("B", "C", 95), _edge("B", "D", 5)]
    got = get_analysis("markov_order_test")(_cubes(grams, edges))
    assert got.headline["excess_information"] == pytest.approx(0.129201, abs=1e-6)


def test_one_row_per_context_with_its_own_divergence():
    """어느 문맥이 1차를 깨는지 보여야 고칠 수 있다."""
    got = get_analysis("markov_order_test")(_cubes(*SECOND_ORDER))
    assert {"prev_state", "state", "cnt", "divergence"} <= set(got.frame.columns)
    frame = got.frame.set_index(["prev_state", "state"])
    assert frame.loc[("A", "B"), "divergence"] == pytest.approx(np.log(2))


def test_the_rows_are_sorted_by_divergence_weighted_by_volume():
    """작은 문맥의 큰 발산이 표 맨 위에 오면 사람이 그걸 결론으로 쓴다."""
    grams = [_gram("A", "B", "C", 1000), _gram("X", "B", "D", 3)]
    edges = [_edge("B", "C", 1000), _edge("B", "D", 3)]
    got = get_analysis("markov_order_test")(_cubes(grams, edges))
    assert got.frame["cnt"].is_monotonic_decreasing


def test_the_other_row_is_excluded_because_it_is_not_a_path():
    """`(other)` 는 여러 경로를 접은 것이라 문맥이 없다."""
    grams = list(SECOND_ORDER[0]) + [
        {**AXES, "n": 3, "path": OTHER_PATH, "cnt": 500, "distinct_dropped": 90}
    ]
    got = get_analysis("markov_order_test")(_cubes(grams, SECOND_ORDER[1]))
    assert OTHER_PATH not in set(got.frame["prev_state"])
    assert got.headline["excess_information"] == pytest.approx(np.log(2))


def test_headline_coverage_says_how_much_of_the_window_was_tested():
    """상위 200 컷 때문에 검정은 남은 경로에 대해서만 성립한다."""
    grams = list(SECOND_ORDER[0]) + [
        {**AXES, "n": 3, "path": OTHER_PATH, "cnt": 100, "distinct_dropped": 90}
    ]
    got = get_analysis("markov_order_test")(_cubes(grams, SECOND_ORDER[1]))
    assert got.headline["coverage"] == pytest.approx(0.5)


def test_a_context_whose_middle_state_is_absent_from_the_edges_is_skipped():
    """1차 예측을 만들 수 없으면 그 문맥은 검정 대상이 아니다 — 0 으로 때우지 않는다."""
    grams = [_gram("A", "B", "C", 50), _gram("A", "Z", "C", 50)]
    edges = [_edge("B", "C", 50)]          # Z 가 없다
    got = get_analysis("markov_order_test")(_cubes(grams, edges))
    assert set(got.frame["state"]) == {"B"}


def test_it_needs_both_cubes():
    """1차 예측은 전이 큐브에서, 관측 3-gram 은 경로 큐브에서 온다."""
    no_path = CubeSet(session=None, transition=pd.DataFrame(SECOND_ORDER[1]),
                      quality=None, state_dict_version="sd_abc", services=["top"],
                      requested_dates=["2026-07-27"], present_dates=["2026-07-27"])
    with pytest.raises(ValueError, match="needs the path cube"):
        get_analysis("markov_order_test")(no_path)

    no_edges = CubeSet(session=None, transition=None, quality=None,
                       state_dict_version="sd_abc", services=["top"],
                       requested_dates=["2026-07-27"], present_dates=["2026-07-27"],
                       path=pd.DataFrame(SECOND_ORDER[0]))
    with pytest.raises(ValueError, match="needs the transition cube"):
        get_analysis("markov_order_test")(no_edges)


def test_segment_split_rows_are_aggregated_before_forming_the_distribution():
    """path 큐브는 세그먼트(축 조합)별로 쪼개져 있다 — 같은 3-gram 이 os·성별·버전마다
    다른 행이다. 관측 분포를 만들기 전에 합치지 않으면 조각 확률이 1차 예측보다 작아
    KL 이 음수가 된다(실데이터에서 excess_information 이 -6.3 nats 로 나왔다).

    A>B>C 를 두 조각(25+25)으로 쪼갠다. 1차가 성립하므로(B 다음은 항상 C) 합친 뒤엔
    0 이어야 한다. 합치지 않으면 (A,B) 문맥의 관측이 조각당 0.5 로 갈려 P(C|B)=1.0 보다
    작아지고 KL = -ln2 로 음수가 된다.
    """
    grams = [_gram("A", "B", "C", 25), _gram("A", "B", "C", 25),
             _gram("X", "B", "C", 50)]
    edges = [_edge("B", "C", 100)]
    got = get_analysis("markov_order_test")(_cubes(grams, edges))
    assert got.headline["excess_information"] == pytest.approx(0.0)
    assert (got.frame["divergence"] >= -1e-9).all(), "KL 은 음수가 될 수 없다"


def test_the_first_order_prediction_comes_from_the_edges_not_the_path_marginal():
    """1차 예측은 전이 큐브에서 온다 — 경로 큐브의 자체 marginal 이 아니다. 검정 대상이
    '이 프로젝트의 마르코프 분석들이 실제로 쓰는 모델'이라야 뜻이 있고, 상위 200 컷이
    물리면 둘이 갈린다(컷이 없으면 같다). 여기선 전이 큐브가 90:10, 경로 marginal 은
    50:50 이라 두 예측이 다른 값을 낸다.

    marginal 로 예측하면 관측(50:50)과 같아져 KL=0 이 되는데, 그건 자기 자신과의 대조라
    '직전 화면이 예측을 개선하는가' 를 못 묻는다.
    """
    grams = [_gram("A", "B", "C", 50), _gram("A", "B", "D", 50)]
    edges = [_edge("B", "C", 90), _edge("B", "D", 10)]
    got = get_analysis("markov_order_test")(_cubes(grams, edges))
    expected = 0.5 * np.log(0.5 / 0.9) + 0.5 * np.log(0.5 / 0.1)  # 전이 예측(90:10) 기준
    assert got.headline["excess_information"] == pytest.approx(expected, abs=1e-6)
    assert got.headline["excess_information"] > 0.1, "경로 marginal 이면 0 이 된다"

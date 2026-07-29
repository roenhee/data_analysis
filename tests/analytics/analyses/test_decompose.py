import pandas as pd
import pytest

from analytics.analyses.base import AnalysisResult, CubeSet, analysis
from analytics.analyses.operators import compare, decompose
from tests.analytics.analyses.test_compare_operator import SIMPSON, _cubes


def test_within_and_between_sum_to_the_pooled_delta():
    """항등식. 안 맞으면 분해가 틀린 것이다."""
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(SIMPSON, c, by=["period"], metric="mean_steps")
    assert d.within + d.between == pytest.approx(c.pooled["mean_steps"], abs=1e-9)


def test_within_is_positive_when_every_stratum_is_positive():
    """실측: 날짜별 전부 +4~6% 인데 합산은 -2.1%. within 이 실제 효과다."""
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(SIMPSON, c, by=["period"], metric="mean_steps")
    assert d.within > 0
    assert d.between < 0          # 구성 변화가 부호를 뒤집었다


def test_within_uses_the_b_side_stratum_weights():
    """가중치를 어느 쪽 층 비중으로 잡느냐를 고정한다.

    **항등식 테스트로는 이걸 못 잡는다** — `between = pooled - within` 이 잔차라서
    `within` 이 무엇이든 합은 맞는다. 그래서 두 가중치가 **부호까지 갈리는** 큐브로
    b 쪽을 못 박는다: 여기서 a 쪽 비중으로 가중하면 -0.098 이 나온다.

    `within` 은 "구성이 b 와 같았다면 델타가 얼마였겠나" 이므로 b 쪽 비중이 맞다.
    """
    split = _cubes([
        ("2026-07-27", "9.5.0", 1000, 10.0), ("2026-07-27", "9.5.1", 10, 11.0),
        ("2026-07-28", "9.5.0", 10, 10.0), ("2026-07-28", "9.5.1", 1000, 9.0),
    ])
    c = compare(split, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(split, c, by=["period"], metric="mean_steps")
    assert d.per_stratum["delta"].tolist() == pytest.approx([0.1, -0.1])
    assert d.within == pytest.approx(0.1 * (990 / 1010))


def test_per_stratum_carries_both_volumes():
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(SIMPSON, c, by=["period"], metric="mean_steps")
    assert {"a_cnt", "b_cnt", "delta"} <= set(d.per_stratum.columns)


def test_composition_reports_the_axis_that_shifted():
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(SIMPSON, c, by=["period"], metric="mean_steps")
    # 실측 daypart 총변동거리 0.064, os 0.038 처럼 축별 어긋남을 낸다
    assert d.composition["period"] > 0.5


def test_a_stratum_present_on_only_one_side_is_reported_not_dropped():
    lop = _cubes([
        ("2026-07-27", "9.5.0", 100, 10.0), ("2026-07-27", "9.5.1", 100, 11.0),
        ("2026-07-28", "9.5.0", 100, 10.0),
    ])
    c = compare(lop, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(lop, c, by=["period"], metric="mean_steps")
    assert "2026-07-28" in set(d.per_stratum["period"])
    assert pd.isna(d.per_stratum.set_index("period").loc["2026-07-28", "delta"])


def test_an_unknown_metric_is_rejected():
    c = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    with pytest.raises(KeyError, match="nope"):
        decompose(SIMPSON, c, by=["period"], metric="nope")


@analysis("fake_steps_power")
def _fake_steps_power(cubes, power: float = 1.0, **params):
    """걸음 수의 `power` 승 평균. params 가 층별 재실행까지 따라오는지 보려고 만들었다."""
    t = cubes.transition
    total = float(t["cnt"].sum()) if len(t) else 0.0
    mean = (float(((t["steps"] ** power) * t["cnt"]).sum() / total)
            if total else float("nan"))
    days = sorted(set(t["period"])) if len(t) else []
    return AnalysisResult(
        frame=t, headline={"mean_steps": mean},
        envelope={"state_dict_version": "sd_abc", "services": ["top"],
                  "requested_dates": days, "present_dates": days,
                  "missing_dates": [], "is_complete": True, "coverage": {},
                  "warnings": []},
    )


def test_the_comparison_params_reach_the_stratum_reruns():
    """`pooled` 를 만든 params 로 층별도 다시 돌려야 한다.

    안 넘기면 층별은 기본값(`power=1`)으로 계산돼 `within` 이 `pooled` 와 **다른 지표**를
    재고, `between = pooled - within` 이 그 차이를 조용히 삼킨다. 항등식은 그래도
    성립하므로 항등식 테스트로는 안 잡힌다.
    """
    doubled = _cubes([
        ("2026-07-27", "9.5.0", 100, 10.0), ("2026-07-27", "9.5.1", 100, 20.0),
        ("2026-07-28", "9.5.0", 100, 10.0), ("2026-07-28", "9.5.1", 100, 20.0),
    ])
    c = compare(doubled, "fake_steps_power", on="app_version",
                a="9.5.1", b="9.5.0", power=2.0)
    assert c.pooled["mean_steps"] == pytest.approx(3.0)        # 400/100 - 1
    d = decompose(doubled, c, by=["period"], metric="mean_steps")
    # power=1 로 다시 돌면 1.0 이 나온다.
    assert d.per_stratum["delta"].tolist() == pytest.approx([3.0, 3.0])
    assert d.within == pytest.approx(3.0)


def test_a_cube_without_a_volume_column_is_refused():
    """물량을 셀 수 없으면 층 가중치가 전부 0 이 되어 `within` 이 0, `between` 이 델타를
    통째로 삼킨다 — "전부 구성 변화" 라고 조용히 보고하게 되므로 막는다.
    """
    from analytics.analyses.operators import Comparison

    novol = CubeSet(
        session=None,
        transition=pd.DataFrame([
            {"period": "2026-07-27", "app_version": v, "steps": s}
            for v, s in (("9.5.0", 10.0), ("9.5.1", 11.0))
        ]),
        quality=None, state_dict_version="sd_abc", services=["top"],
        requested_dates=["2026-07-27"], present_dates=["2026-07-27"],
    )
    c = Comparison(
        pooled={"mean_steps": 0.1}, per_day=pd.DataFrame(), weight_skew=0.0,
        dates_used=["2026-07-27"], date_reason="test", sign_disagrees=False,
        result=AnalysisResult(
            frame=pd.DataFrame(), headline={"mean_steps": 0.1},
            envelope={"comparison": {"on": "app_version", "a": "9.5.1",
                                     "b": "9.5.0"}},
        ),
        analysis_name="fake_steps",
    )
    with pytest.raises(ValueError, match="cnt"):
        decompose(novol, c, by=["period"], metric="mean_steps")

import pandas as pd
import pytest

from analytics.analyses.base import AnalysisResult, CubeSet, analysis
from analytics.analyses.operators import compare


@analysis("fake_steps")
def _fake_steps(cubes, **params):
    """전이 수로 가중한 평균 걸음 수 — 테스트용 가짜 분석."""
    t = cubes.transition
    total = float(t["cnt"].sum()) if len(t) else 0.0
    mean = float((t["steps"] * t["cnt"]).sum() / total) if total else float("nan")
    days = sorted(set(t["period"])) if len(t) else []
    return AnalysisResult(
        frame=t, headline={"mean_steps": mean},
        envelope={"state_dict_version": "sd_abc", "services": ["top"],
                  "requested_dates": days, "present_dates": days,
                  "missing_dates": [], "is_complete": True, "coverage": {},
                  "warnings": []},
    )


def _cubes(rows) -> CubeSet:
    t = pd.DataFrame(
        [{"period": p, "app_version": v, "cnt": c, "steps": s} for p, v, c, s in rows]
    )
    days = sorted(set(t["period"]))
    return CubeSet(session=None, transition=t, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=days, present_dates=days)


# 실측 재현(2026-07-26~28, MA): 날짜별로는 전부 9.5.1 이 크고, 합치면 뒤집힌다.
# 물량은 백만 단위 실측을 그대로 옮겼다.
SIMPSON = _cubes([
    ("2026-07-26", "9.5.0", 143, 13.2), ("2026-07-26", "9.5.1", 3, 14.0),
    ("2026-07-27", "9.5.0", 73, 12.3), ("2026-07-27", "9.5.1", 87, 12.8),
    ("2026-07-28", "9.5.0", 26, 11.5), ("2026-07-28", "9.5.1", 139, 12.2),
])


def test_per_day_deltas_are_returned_alongside_the_pooled_one():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert len(got.per_day) == 3
    assert set(got.per_day["period"]) == {"2026-07-26", "2026-07-27", "2026-07-28"}


def test_the_pooled_delta_can_disagree_with_every_day():
    """심슨의 역설. 실측에서 날짜별 +6.4/+4.0/+6.3% 인데 합산은 -2.1% 였다.

    합산 숫자 하나만 내면 "9.5.1 에서 세션이 짧아졌다" 고 정반대로 보고하게 된다.
    """
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert (got.per_day["delta_mean_steps"] > 0).all()
    assert got.pooled["mean_steps"] < 0
    assert got.sign_disagrees is True


def test_sign_agreement_is_reported_when_they_agree():
    even = _cubes([
        ("2026-07-27", "9.5.0", 100, 10.0), ("2026-07-27", "9.5.1", 100, 11.0),
        ("2026-07-28", "9.5.0", 100, 10.0), ("2026-07-28", "9.5.1", 100, 11.0),
    ])
    got = compare(even, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert got.sign_disagrees is False
    assert got.pooled["mean_steps"] == pytest.approx(0.1)


def test_weight_skew_is_reported():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert got.weight_skew > 0.5


def test_dates_used_are_recorded_with_the_reason():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert got.dates_used == ["2026-07-26", "2026-07-27", "2026-07-28"]
    assert "overlap" in got.date_reason


def test_release_dates_exclude_pre_release_traffic():
    """배포 전 트래픽은 적은 표본이 아니라 다른 모집단(테스터)이다."""
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0",
                  released={"9.5.1": "2026-07-27"})
    assert got.dates_used == ["2026-07-27", "2026-07-28"]
    assert "release" in got.date_reason


def test_a_disjoint_comparison_is_refused():
    from analytics.metrics.compare import ConfoundedComparisonError
    disjoint = _cubes([
        ("2026-07-26", "9.5.0", 100, 10.0), ("2026-07-28", "9.5.1", 100, 11.0),
    ])
    with pytest.raises(ConfoundedComparisonError, match="no overlapping"):
        compare(disjoint, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")


def test_the_envelope_records_both_segments_and_the_dates():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    for key in ("state_dict_version", "coverage", "services", "present_dates"):
        assert key in got.result.envelope
    assert got.result.envelope["comparison"] == {
        "on": "app_version", "a": "9.5.1", "b": "9.5.0",
    }


def test_the_analysis_name_is_kept_so_decompose_can_rerun_it():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert got.analysis_name == "fake_steps"


def test_compare_works_on_any_registered_analysis_by_name():
    got = compare(SIMPSON, "fake_steps", on="app_version", a="9.5.1", b="9.5.0")
    assert "mean_steps" in got.pooled

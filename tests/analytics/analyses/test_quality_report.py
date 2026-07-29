import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

# 분모를 일부러 다르게 둔다(top 1000, news 4000). 같으면 "비율의 평균" 과
# "카운트에서 유도한 비율" 이 우연히 같아져 그 구분을 검증할 수 없다.
CHECKS = [
    ("2026-07-27", "top", "session_no_screen", 255, 1000),
    ("2026-07-27", "news", "session_no_screen", 12, 4000),
    ("2026-07-27", "top", "exit_without_appexit", 108, 1000),
    ("2026-07-28", "top", "session_no_screen", 300, 1000),
    ("2026-07-28", "news", "session_no_screen", 20, 4000),
    ("2026-07-28", "top", "exit_without_appexit", 100, 1000),
]


def _quality(rows=CHECKS) -> pd.DataFrame:
    return pd.DataFrame([
        {"period": p, "service_code": s, "app_version": "9.5.1",
         "check_name": c, "violated": v, "total": t}
        for p, s, c, v, t in rows
    ])


def _cubes(rows=CHECKS) -> CubeSet:
    return CubeSet(session=None, transition=None, quality=_quality(rows),
                   state_dict_version="sd_abc", services=["top", "news"],
                   requested_dates=["2026-07-27", "2026-07-28"],
                   present_dates=["2026-07-27", "2026-07-28"])


def test_one_row_per_check_and_date():
    got = get_analysis("quality_report")(_cubes())
    assert len(got.frame) == 4
    assert set(got.frame["check_name"]) == {"session_no_screen",
                                            "exit_without_appexit"}


def test_ratio_is_derived_not_stored():
    """서비스별 행을 합칠 때 비율을 평균하면 분모를 무시하게 된다.

    07-27 의 session_no_screen 은 255/1000 과 12/4000 을 합친 267/5000 = 5.34% 다.
    두 비율의 평균은 (25.5% + 0.3%)/2 = 12.9% 로 2.4배 크다 — news 의 큰 분모가
    사라지기 때문이다. 그래서 카운트를 합치고 나서 나눈다.
    """
    got = get_analysis("quality_report")(_cubes()).frame
    row = got[(got["check_name"] == "session_no_screen")
              & (got["period"] == "2026-07-27")].iloc[0]
    assert row["violated"] == 267
    assert row["total"] == 5000
    assert row["ratio"] == pytest.approx(267 / 5000)


def test_headline_carries_the_worst_ratio_per_check():
    got = get_analysis("quality_report")(_cubes())
    # session_no_screen: 07-27 0.0534, 07-28 0.064 -> 최악 0.064
    assert got.headline["worst_session_no_screen"] == pytest.approx(0.064)
    assert got.headline["worst_exit_without_appexit"] == pytest.approx(0.108)


def test_exit_corroboration_is_reported_as_a_positive_number():
    """이탈 정의의 뒷받침 정도 = 1 - exit_without_appexit. 실측 89.2%."""
    got = get_analysis("quality_report")(_cubes())
    assert got.headline["exit_corroboration"] == pytest.approx(1 - 208 / 2000)


def test_warnings_fire_above_the_configured_threshold():
    got = get_analysis("quality_report")(
        _cubes(), thresholds={"session_no_screen": 0.10}
    )
    fired = [w for w in got.envelope["warnings"]
             if w["check_name"] == "session_no_screen"]
    # top 은 두 날 모두 넘고(0.255, 0.30) news 는 두 날 모두 안 넘는다(0.012, 0.02).
    assert len(fired) == 2
    assert all(w["service_code"] == "top" for w in fired)


def test_thresholds_default_to_the_shipped_config():
    from analytics.metrics.load import load_quality_thresholds

    shipped = load_quality_thresholds()
    bad = _cubes(CHECKS + [("2026-07-28", "cafe", "session_no_screen", 500, 1000)])
    got = get_analysis("quality_report")(bad)
    fired = [w for w in got.envelope["warnings"]
             if w["service_code"] == "cafe"]
    assert len(fired) == 1
    assert fired[0]["threshold"] == pytest.approx(shipped["session_no_screen"])


def test_an_unthresholded_check_is_reported_but_not_warned_about():
    """임계치를 발명하지 않는다 — 측정된 기저가 없는 검사는 표에만 낸다."""
    rows = CHECKS + [("2026-07-27", "top", "page_name_ambiguous", 900, 1000)]
    got = get_analysis("quality_report")(_cubes(rows))
    assert "page_name_ambiguous" in set(got.frame["check_name"])
    assert not [w for w in got.envelope["warnings"]
                if w["check_name"] == "page_name_ambiguous"]


def test_the_envelope_carries_screen_coverage():
    got = get_analysis("quality_report")(_cubes())
    assert got.envelope["coverage"]["screen"] == pytest.approx(1 - 587 / 10000)


def test_a_check_with_no_denominator_is_nan_not_zero():
    rows = [("2026-07-27", "top", "session_no_screen", 0, 0)]
    got = get_analysis("quality_report")(_cubes(rows))
    assert pd.isna(got.frame["ratio"].iloc[0])

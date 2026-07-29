"""세션 큐브 분석을 연산자에 걸 수 있는가. 물량 컬럼이 큐브마다 다른 것이 요점이다."""
import numpy as np
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis
from analytics.analyses.operators import compare, decompose

AXES = ("period", "service_type", "os", "gender", "age_band", "daypart",
        "app_version")

# 하루 · 버전당: 전체 조합 행 둘(gender M/F, 각 100세션) + gender 를 접은 행 하나(200세션).
# 접은 행은 app_version 을 그대로 갖고 있어서, 전체 조합 행만 세지 않으면 물량이 2배가 된다.
# 9.5.0 은 세션당 600초, 9.5.1 은 660초 -> 델타 +10% (두 날 모두).
def _session_cube() -> pd.DataFrame:
    base = dict(service_type="MA", os="android", age_band="50", daypart="12~17")
    rows = []
    for day in ("2026-07-27", "2026-07-28"):
        for version, seconds in (("9.5.0", 600.0), ("9.5.1", 660.0)):
            for gender in ("M", "F"):
                rows.append({**base, "period": day, "gender": gender,
                             "app_version": version, "sessions": 100, "uv": 60,
                             "pv": 800, "events": 3000,
                             "duration_sum": int(100 * seconds)})
            rows.append({**base, "period": day, "gender": None,
                         "app_version": version, "sessions": 200, "uv": 110,
                         "pv": 1600, "events": 6000,
                         "duration_sum": int(200 * seconds)})
        # (period) 롤업 행 — 자르지 않은 프레임에서 uv 를 읽는 행
        rows.append({**{a: None for a in AXES}, "period": day, "sessions": 400,
                     "uv": 200, "pv": 3200, "events": 12000,
                     "duration_sum": 252_000})
    return pd.DataFrame(rows)


def _cubes() -> CubeSet:
    days = ["2026-07-27", "2026-07-28"]
    return CubeSet(session=_session_cube(), transition=None, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=days, present_dates=days)


def test_a_session_cube_analysis_can_be_compared():
    got = compare(_cubes(), "session_trend", on="app_version", a="9.5.1", b="9.5.0")
    assert got.dates_used == ["2026-07-27", "2026-07-28"]
    assert got.pooled["seconds_per_session"] == pytest.approx(0.1)
    assert got.per_day["delta_seconds_per_session"].tolist() == pytest.approx([0.1, 0.1])
    assert got.sign_disagrees is False


def test_the_day_weights_count_sessions_not_transitions():
    """전이 큐브에만 있는 `cnt` 로 세면 `KeyError` 다. 세션 큐브는 `sessions` 로 센다."""
    got = compare(_cubes(), "session_trend", on="app_version", a="9.5.1", b="9.5.0")
    assert got.weight_skew == pytest.approx(0.0)


def test_the_stratum_volume_excludes_rollup_rows():
    """롤업 행을 함께 세면 물량이 2배가 된다 — 사람이 읽는 표에 없는 세션이 실린다."""
    c = compare(_cubes(), "session_trend", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(_cubes(), c, by=["period"], metric="seconds_per_session")
    per = d.per_stratum.set_index("period")
    assert per.loc["2026-07-27", "a_cnt"] == pytest.approx(200.0)
    assert per.loc["2026-07-27", "b_cnt"] == pytest.approx(200.0)


def test_the_decomposition_identity_holds_on_a_session_cube():
    c = compare(_cubes(), "session_trend", on="app_version", a="9.5.1", b="9.5.0")
    d = decompose(_cubes(), c, by=["period"], metric="seconds_per_session")
    assert d.within + d.between == pytest.approx(c.pooled["seconds_per_session"],
                                                 abs=1e-9)
    assert d.within == pytest.approx(0.1)

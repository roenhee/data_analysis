"""봉투가 합산 지표의 서비스 구성을 싣는다.

`per_service` 를 **부른 사람만** 구성을 아는 게 문제였다. 합산 결과를 그냥 받은 사람은
`mean_expected_steps` 10.62 를 "앱 전체" 로 읽는데 실제로는 서비스별 2.77~8.08 이고 top 이
61.8% 다. 봉투는 이미 커버리지·사전 버전·날짜를 싣고 있으니 구성도 여기 넣는다.
"""
import pandas as pd
import pytest

from analytics.analyses.base import (
    REQUIRED_ENVELOPE_KEYS,
    CubeSet,
    envelope_for,
    get_analysis,
)

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _cubes(session=None, transition=None, quality=None) -> CubeSet:
    return CubeSet(session=session, transition=transition, quality=quality,
                   state_dict_version="sd_abc", services=["top", "media"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


def _edges() -> pd.DataFrame:
    return pd.DataFrame([
        {**AXES, "from_state": "top/a", "to_state": "media/x", "cnt": 800,
         "dur_sum": 8000.0, "dur_n": 800},
        {**AXES, "from_state": "media/x", "to_state": "EXIT", "cnt": 200,
         "dur_sum": 2000.0, "dur_n": 200},
    ])


def test_the_envelope_carries_the_service_mix():
    got = envelope_for(_cubes(transition=_edges()), {})
    assert got["service_mix"] == {"top": pytest.approx(0.8),
                                  "media": pytest.approx(0.2)}


def test_a_shipped_analysis_carries_it_too():
    got = get_analysis("screen_flow")(_cubes(transition=_edges()))
    assert got.envelope["service_mix"]["top"] == pytest.approx(0.8)


def test_a_cube_without_a_transition_frame_gets_an_empty_mix():
    """세션 큐브만 있으면 서비스를 알 수 없다. 빈 dict 이고 0 으로 채우지 않는다."""
    session = pd.DataFrame([{**AXES, "sessions": 10, "uv": 5, "pv": 80,
                             "events": 300, "duration_sum": 6000}])
    assert envelope_for(_cubes(session=session), {})["service_mix"] == {}


def test_the_quality_cube_supplies_the_mix_when_there_are_no_edges():
    """품질 큐브에는 `service_code` 가 정식 컬럼으로 있다."""
    quality = pd.DataFrame([
        {"service_code": "top", "app_version": "9.5.1", "period": "2026-07-27",
         "check_name": "null_action_name", "violated": 1, "total": 800},
        {"service_code": "media", "app_version": "9.5.1", "period": "2026-07-27",
         "check_name": "null_action_name", "violated": 1, "total": 200},
    ])
    got = envelope_for(_cubes(quality=quality), {})
    assert got["service_mix"] == {"top": pytest.approx(0.8),
                                  "media": pytest.approx(0.2)}


def test_service_mix_is_not_required_to_publish():
    """세션 큐브만 있는 분석은 구성을 알 수 없다. 필수 키로 만들면 발행이 막힌다."""
    assert "service_mix" not in REQUIRED_ENVELOPE_KEYS

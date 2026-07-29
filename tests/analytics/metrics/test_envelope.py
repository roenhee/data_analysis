import pandas as pd
import pytest

from analytics.metrics.envelope import Envelope, quality_warnings


def _quality() -> pd.DataFrame:
    return pd.DataFrame([
        {"service_code": "top", "app_version": "9.5.1",
         "check_name": "null_action_name", "violated": 198, "total": 1000},
        {"service_code": "top", "app_version": "9.5.1",
         "check_name": "screen_without_dwell", "violated": 430, "total": 1000},
        {"service_code": "top", "app_version": "9.5.1",
         "check_name": "session_no_screen", "violated": 5, "total": 1000},
    ])


def test_warnings_fire_above_the_threshold():
    got = quality_warnings(_quality(), thresholds={"null_action_name": 0.1})
    assert len(got) == 1
    assert got[0]["check_name"] == "null_action_name"
    assert got[0]["ratio"] == pytest.approx(0.198)


def test_a_warning_carries_its_denominator():
    """비율만 내면 3건 중 3건과 300만 중 300만이 같게 보인다.

    실측에서 롱테일 앱 버전들이 `session_no_screen` 100% 를 찍는데 세션은 한 자리 수다.
    """
    got = quality_warnings(_quality(), thresholds={"null_action_name": 0.1})
    assert got[0]["total"] == pytest.approx(1000.0)


def test_a_warning_identifies_itself_with_whatever_keys_the_frame_has():
    """호출자가 어느 수준으로 집계해 넘겼는지에 따라 식별 컬럼이 다르다.

    버전을 접은 프레임에는 `app_version` 이 없고 `period` 가 있다. 없는 컬럼을 `None`
    으로 채우면 "버전 미상" 처럼 읽히므로, 있는 것만 낸다.
    """
    folded = pd.DataFrame([
        {"service_code": "top", "period": "2026-07-27",
         "check_name": "null_action_name", "violated": 198, "total": 1000},
    ])
    got = quality_warnings(folded, thresholds={"null_action_name": 0.1})
    assert got[0]["period"] == "2026-07-27"
    assert "app_version" not in got[0]

    raw = quality_warnings(_quality(), thresholds={"null_action_name": 0.1})
    assert raw[0]["app_version"] == "9.5.1"
    assert "period" not in raw[0]


def test_warnings_stay_silent_below_the_threshold():
    assert quality_warnings(_quality(), thresholds={"session_no_screen": 0.5}) == []


def test_a_check_with_no_threshold_is_not_a_warning():
    assert quality_warnings(_quality(), thresholds={}) == []


def test_zero_total_does_not_divide_by_zero():
    frame = pd.DataFrame([
        {"service_code": "top", "app_version": "9.5.1",
         "check_name": "null_action_name", "violated": 0, "total": 0},
    ])
    assert quality_warnings(frame, thresholds={"null_action_name": 0.0}) == []


def test_several_checks_can_warn_at_once():
    got = quality_warnings(
        _quality(),
        thresholds={"null_action_name": 0.1, "screen_without_dwell": 0.3},
    )
    assert {w["check_name"] for w in got} == {
        "null_action_name", "screen_without_dwell",
    }


def test_envelope_carries_everything_the_spec_requires():
    env = Envelope(
        state_dict_version="sd_abc",
        services=["top", "media"],
        requested_dates=["2026-07-26", "2026-07-27"],
        present_dates=["2026-07-26", "2026-07-27"],
        coverage={"dwell": 0.57},
        warnings=[],
    )
    d = env.as_dict()
    for key in ("state_dict_version", "services", "requested_dates",
                "present_dates", "missing_dates", "coverage", "warnings"):
        assert key in d


def test_envelope_derives_missing_dates():
    env = Envelope(
        state_dict_version="sd_abc",
        services=["top"],
        requested_dates=["2026-07-26", "2026-07-27"],
        present_dates=["2026-07-26"],
        coverage={},
        warnings=[],
    )
    assert env.as_dict()["missing_dates"] == ["2026-07-27"]
    assert env.as_dict()["is_complete"] is False


def test_envelope_records_the_service_scope_because_the_cube_does_not():
    # 세션의 44.7% 가 여러 서비스에 걸쳐서 service_code 가 세션 큐브의 축이 될 수 없다.
    # 그래서 "이 숫자가 어떤 서비스 범위인가"는 봉투에만 있다.
    env = Envelope(
        state_dict_version="sd_abc", services=["top", "media"],
        requested_dates=[], present_dates=[], coverage={}, warnings=[],
    )
    assert env.as_dict()["services"] == ["top", "media"]


def test_envelope_from_a_loaded_cube_copies_the_date_bookkeeping():
    from analytics.metrics.load import LoadedCube

    loaded = LoadedCube(
        frame=pd.DataFrame(),
        requested_dates=["2026-07-26", "2026-07-27"],
        present_dates=["2026-07-26"],
        missing_dates=["2026-07-27"],
    )
    env = Envelope.for_cube(loaded, state_dict_version="sd_abc", services=["top"])
    assert env.missing_dates == ["2026-07-27"]
    assert env.as_dict()["is_complete"] is False

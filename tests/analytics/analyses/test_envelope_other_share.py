"""봉투가 서비스별 `/other` 비중을 싣고, 큰 서비스를 경고한다.

`/other` 는 드문 화면이 아니라 **여러 화면을 하나로 접은 가짜 화면**이다. 전체로는 4.71%라
무시할 만해 보이지만 sports 36.97% · entertain 18.67% 이고, 그 서비스에서는 화면 상태가
둘뿐인데 하나가 이 버킷이다. 원래 마르코프 노트북이 재던 값인데 파이프라인이 잃었다.
"""
import pandas as pd
import pytest

from analytics.analyses.base import (
    OTHER_WARN_ABOVE,
    REQUIRED_ENVELOPE_KEYS,
    CubeSet,
    envelope_for,
    get_analysis,
)

AXES = dict(period="2026-07-27", service_type="MA", os="android", gender="M",
            age_band="50", daypart="12~17", app_version="9.5.1")


def _edge(f: str, t: str, cnt: int) -> dict:
    return {**AXES, "from_state": f, "to_state": t, "cnt": cnt,
            "dur_sum": float(cnt) * 10.0, "dur_n": cnt}


def _cubes(rows) -> CubeSet:
    return CubeSet(session=None, transition=pd.DataFrame(rows), quality=None,
                   state_dict_version="sd_abc", services=["top", "sports"],
                   requested_dates=["2026-07-27"], present_dates=["2026-07-27"])


# top 은 `/other` 가 10%, sports 는 70% — 실측의 비대칭을 축소한 것이다.
LUMPED = [
    _edge("START", "top/엠탑조회", 5000),
    _edge("top/엠탑조회", "top/홈탭_진입", 900),
    _edge("top/other", "top/엠탑조회", 100),
    _edge("sports/m_newsview_보기", "EXIT", 300),
    _edge("sports/other", "sports/m_newsview_보기", 700),
]


def test_the_envelope_carries_the_other_share_per_service():
    got = envelope_for(_cubes(LUMPED), {})
    assert got["other_share"] == {"top": pytest.approx(0.1),
                                  "sports": pytest.approx(0.7)}


def test_a_shipped_analysis_carries_it_too():
    got = get_analysis("screen_flow")(_cubes(LUMPED))
    assert got.envelope["other_share"]["sports"] == pytest.approx(0.7)


def test_a_service_over_the_threshold_is_warned_about():
    """임계치는 실측 나쁜 무리(sports 36.97% · entertain 18.67%) 최솟값 아래에 둔다."""
    got = envelope_for(_cubes(LUMPED), {})
    lumped = [w for w in got["warnings"]
              if w["check_name"] == "screens_lumped_into_other"]
    assert len(lumped) == 1
    assert lumped[0]["service_code"] == "sports"
    assert lumped[0]["ratio"] == pytest.approx(0.7)
    assert lumped[0]["threshold"] == pytest.approx(OTHER_WARN_ABOVE)


def test_the_threshold_sits_below_the_measured_bad_cluster():
    """규칙: 관측 최댓값 위(드리프트) 아니면 나쁜 무리 최솟값 아래(상시 표시).

    실측 무리는 {0, 0.003%, 0.52%, 3.05%, 18.67%, 36.97%} 이고 나쁜 쪽 최솟값이
    18.67% 다. 사이에 두면 정상 변동의 상위 몇 서비스만 걸린다.
    """
    assert 0.0305 < OTHER_WARN_ABOVE < 0.1867


def test_the_analysis_keeps_its_own_warnings_alongside():
    """봉투가 경고를 덧붙이면서 분석이 낸 경고를 덮어쓰면 안 된다."""
    got = envelope_for(_cubes(LUMPED), {}, [{"check_name": "thin_transition_cells"}])
    names = [w["check_name"] for w in got["warnings"]]
    assert names == ["thin_transition_cells", "screens_lumped_into_other"]


def test_a_cube_with_no_other_bucket_gets_no_warning():
    rows = [_edge("top/엠탑조회", "EXIT", 1000)]
    got = envelope_for(_cubes(rows), {})
    assert got["other_share"] == {"top": 0.0}
    assert got["warnings"] == []


def test_a_session_only_cube_gets_an_empty_other_share():
    """세션 큐브에는 화면 이름이 없다. 빈 dict 이고 0 으로 채우지 않는다."""
    session = pd.DataFrame([{**AXES, "sessions": 10, "uv": 5, "pv": 80,
                             "events": 300, "duration_sum": 6000}])
    got = envelope_for(
        CubeSet(session=session, transition=None, quality=None,
                state_dict_version="sd_abc", services=["top"],
                requested_dates=["2026-07-27"], present_dates=["2026-07-27"]),
        {},
    )
    assert got["other_share"] == {}
    assert got["warnings"] == []


def test_other_share_is_not_required_to_publish():
    """전이 큐브가 없는 분석은 알 수 없다. 필수 키로 만들면 발행이 막힌다."""
    assert "other_share" not in REQUIRED_ENVELOPE_KEYS

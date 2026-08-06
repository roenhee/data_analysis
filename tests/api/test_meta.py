"""meta: 카탈로그·세그먼트 축·present_dates."""
from analytics.analyses.base import get_analysis, list_analyses

from api import meta


def test_build_meta_has_catalog_and_axes():
    m = meta.build_meta()
    names = [a["name"] for a in m["analyses"]]
    assert "session_trend" in names
    # 한글 라벨이 붙는다.
    st_entry = next(a for a in m["analyses"] if a["name"] == "session_trend")
    assert st_entry["label"] and st_entry["label"] != "session_trend"
    # 세그먼트 축 6개.
    axes = [s["axis"] for s in m["segments"]]
    assert set(axes) == {"service_type", "app_version", "os",
                         "gender", "age_band", "daypart"}
    # 파라미터 있는 분석은 params 를 싣는다.
    flow = next(a for a in m["analyses"] if a["name"] == "screen_flow")
    assert any(p["name"] == "damping" for p in flow["params"])


def test_build_meta_present_dates_and_services():
    m = meta.build_meta()
    assert m["present_dates"], "빌드된 날짜가 있어야 한다"
    assert "2026-07-14" in m["present_dates"]
    assert set(m["present_services"]) >= {"top", "search"}


def test_load_session_is_cached_same_object():
    a = meta._load_session("2026-07-14", "2026-07-28")
    b = meta._load_session("2026-07-14", "2026-07-28")
    assert a is b


def test_tabs_cover_exactly_the_registered_analyses():
    # 탭 목록과 레지스트리가 어긋나면 분석이 추가/삭제돼도 조용히 새거나 넘친다.
    # list_analyses() 는 프로세스 전역 레지스트리라, 전체 스위트를 돌리면 다른 테스트
    # 파일이 @analysis 로 등록해 둔 더미(예: test_base.py 의 dummy_with_knobs)도 같이
    # 잡힌다 — analytics/analyses/ 밑에 실제로 정의된 것만 걸러서 비교한다.
    production = {
        name for name in list_analyses()
        if get_analysis(name).__module__.startswith("analytics.analyses.")
    }
    assert set().union(*meta.TABS.values()) == production


def test_build_meta_tabs_and_defaults_shape():
    m = meta.build_meta()
    assert m["tabs"], "탭이 있어야 한다"
    for t in m["tabs"]:
        assert {"key", "label", "analyses"} <= set(t)
    assert m["defaults"]["analysis"] == "session_trend"

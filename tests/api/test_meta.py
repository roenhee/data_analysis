"""meta: 카탈로그·세그먼트 축·present_dates."""
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

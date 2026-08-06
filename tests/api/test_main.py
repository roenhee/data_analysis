"""main: 라우팅·400/404·통합."""
from starlette.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_meta_endpoint():
    r = client.get("/api/meta")
    assert r.status_code == 200
    assert "session_trend" in [a["name"] for a in r.json()["analyses"]]


def test_analysis_endpoint_session_trend():
    r = client.get("/api/analysis/session_trend",
                   params={"start": "2026-07-14", "end": "2026-07-16"})
    assert r.status_code == 200
    body = r.json()
    assert body["headline"]
    assert body["viz"]["encoding"]["x"] is not None


def test_missing_required_param_is_400():
    # path_ranking 은 n(required)이 필요하다.
    r = client.get("/api/analysis/path_ranking",
                   params={"start": "2026-07-14", "end": "2026-07-16"})
    assert r.status_code == 400
    assert "n" in r.text


def test_period_over_hard_limit_is_400():
    r = client.get("/api/analysis/session_trend",
                   params={"start": "2026-01-01", "end": "2026-12-31"})
    assert r.status_code == 400


def test_unknown_analysis_is_404():
    r = client.get("/api/analysis/no_such_analysis",
                   params={"start": "2026-07-14", "end": "2026-07-16"})
    assert r.status_code == 404


def test_reversed_range_is_400():
    # start 가 end 보다 나중이면 cube_store.load 가 ValueError 를 낸다 — 500 이 아니라 400.
    r = client.get("/api/analysis/session_trend",
                   params={"start": "2026-07-16", "end": "2026-07-14"})
    assert r.status_code == 400


def test_malformed_date_is_400():
    # date.fromisoformat 이 ValueError 를 낸다 — 클라이언트 입력 오류는 400.
    r = client.get("/api/analysis/session_trend",
                   params={"start": "not-a-date", "end": "2026-07-16"})
    assert r.status_code == 400


def test_non_numeric_param_is_400():
    # path_ranking 의 n 은 int — "abc" 는 params.coerce 에서 ValueError.
    r = client.get("/api/analysis/path_ranking",
                   params={"start": "2026-07-14", "end": "2026-07-16", "n": "abc"})
    assert r.status_code == 400


def test_segment_axis_filters():
    # 반복 쿼리(os=android)가 filters.SEGMENT_AXES 를 타고 세그먼트 필터로 전달돼야 한다.
    unfiltered = client.get("/api/analysis/session_trend",
                            params={"start": "2026-07-14", "end": "2026-07-16"})
    filtered = client.get("/api/analysis/session_trend",
                          params={"start": "2026-07-14", "end": "2026-07-16",
                                  "os": "android"})
    assert filtered.status_code == 200
    fbody = filtered.json()
    assert fbody["headline"]
    assert fbody["rows"]
    # os 로 좁히면 전체 모집단과 다른 결과가 나와야 한다 — 세그먼트가 조용히
    # 버려지는 회귀를 잡는다.
    assert fbody != unfiltered.json()

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

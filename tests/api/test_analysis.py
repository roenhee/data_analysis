"""analysis: JSON 직렬화·Vega-Lite viz·실제 실행."""
import math

import pandas as pd

from analytics.analyses.base import AnalysisResult
from api import analysis


def _synthetic_line_result():
    frame = pd.DataFrame({
        "period": ["2026-07-14", "2026-07-15"],
        "sessions": [100, 120],
        "seconds_per_session": [10.5, float("nan")],
    })
    return AnalysisResult(
        frame=frame,
        headline={"sessions": 220.0, "seconds_per_session": float("nan")},
        envelope={"warnings": [], "coverage": {}, "present_dates":
                  ["2026-07-14", "2026-07-15"], "state_dict_version": "sd_x"},
        compare_key="period",
        viz={"kind": "line", "x": "period"},
    )


def test_result_to_json_shape():
    out = analysis.result_to_json(_synthetic_line_result(), period_days_value=2)
    assert {"headline", "columns", "rows", "viz", "envelope"} <= set(out)
    # headline: NaN 은 render.headline_cards 가 건너뛰므로 sessions 만 남는다.
    labels = [h["label"] for h in out["headline"]]
    assert any("sessions" in lbl or "세션" in lbl for lbl in labels)
    # rows: NaN → None 으로 직렬화(JSON 안전).
    assert out["rows"][1][2] is None
    assert out["envelope"]["period_days"] == 2


def test_result_to_json_soft_limit_warning():
    out = analysis.result_to_json(_synthetic_line_result(), period_days_value=40)
    assert any("한 달" in w for w in out["envelope"]["warnings"])


def test_vega_spec_line_is_vega_lite_dict():
    spec = analysis.vega_spec(_synthetic_line_result())
    assert spec["mark"]["type"] == "line" or spec.get("mark") == "line" \
        or spec["mark"]["type"] == "line"
    assert "encoding" in spec


_SERVICES = ("top", "media", "entertain", "sports", "content_v", "search")


def test_run_session_trend_real_cube():
    out = analysis.run_analysis(
        "session_trend", "2026-07-14", "2026-07-16",
        {"services": list(_SERVICES)}, {}, "sd_2ab5ec25e750dda2")
    # headline 에 세션 수가 있고, viz 는 라인 차트 스펙이다.
    assert out["headline"], "headline 이 비면 안 된다"
    assert out["viz"]["encoding"]["x"] is not None
    assert len(out["rows"]) >= 1

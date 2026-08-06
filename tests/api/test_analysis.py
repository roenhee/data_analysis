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
    assert spec["mark"]["type"] == "line"
    assert "encoding" in spec


def _synthetic_bar_result():
    frame = pd.DataFrame({
        "state": ["home", "search", "player"],
        "seconds_per_visit": [12.0, 8.5, 20.1],
    })
    return AnalysisResult(
        frame=frame, headline={"n": 3.0}, compare_key="state",
        envelope={"warnings": [], "coverage": {}, "present_dates":
                  ["2026-07-14"], "state_dict_version": "sd_x"},
        viz={"kind": "bar", "x": "state"},
    )


def test_vega_spec_bar_is_vega_lite_dict():
    spec = analysis.vega_spec(_synthetic_bar_result())
    # bar_chart 는 mark_bar(color=...) — 추가 속성 때문에 mark 가 dict 로 실린다.
    assert spec["mark"]["type"] == "bar"
    assert "encoding" in spec


def _synthetic_heatmap_result():
    frame = pd.DataFrame({
        "from_state": ["home", "home", "search"],
        "to_state": ["search", "player", "player"],
        "cnt": [10, 5, 7],
    })
    return AnalysisResult(
        frame=frame, headline={"n": 3.0}, compare_key=None,
        envelope={"warnings": [], "coverage": {}, "present_dates":
                  ["2026-07-14"], "state_dict_version": "sd_x"},
        viz={"kind": "heatmap", "x": "from_state", "value": "cnt"},
    )


def test_vega_spec_heatmap_is_vega_lite_dict():
    spec = analysis.vega_spec(_synthetic_heatmap_result())
    # heatmap_chart 는 mark_rect() — 인자가 없어도 Altair 는 {"type": "rect"} 딕셔너리를 낸다.
    assert spec["mark"]["type"] == "rect"
    assert "encoding" in spec


def _synthetic_graph_result():
    # screen_communities(analytics/analyses/communities.py) 의 실제 산출 형태를 그대로 흉내:
    # frame 은 state/community/degree/community_size, viz 는 kind=graph + edges 리스트.
    frame = pd.DataFrame({
        "state": ["A", "B"],
        "community": [0, 0],
        "degree": [3.0, 2.0],
        "community_size": [2, 2],
    })
    return AnalysisResult(
        frame=frame, headline={"communities": 1.0}, compare_key="state",
        envelope={"warnings": [], "coverage": {}, "present_dates":
                  ["2026-07-14"], "state_dict_version": "sd_x"},
        viz={"kind": "graph", "x": "state", "edges": [("A", "B", 1.0)]},
    )


def test_vega_spec_graph_is_passthrough_dict():
    spec = analysis.vega_spec(_synthetic_graph_result())
    # 그래프는 Vega-Lite 스펙이 아니라 노드/엣지 원본 그대로다 — mark/encoding 이 없다.
    assert spec == {"kind": "graph", "x": "state", "edges": [("A", "B", 1.0)]}
    assert "mark" not in spec
    assert "encoding" not in spec


_SERVICES = ("top", "media", "entertain", "sports", "content_v", "search")


def test_run_session_trend_real_cube():
    out = analysis.run_analysis(
        "session_trend", "2026-07-14", "2026-07-16",
        {"services": list(_SERVICES)}, {}, "sd_2ab5ec25e750dda2")
    # headline 에 세션 수가 있고, viz 는 라인 차트 스펙이다.
    assert out["headline"], "headline 이 비면 안 된다"
    assert out["viz"]["encoding"]["x"] is not None
    assert len(out["rows"]) >= 1

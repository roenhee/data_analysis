"""FastAPI 앱: /api/meta, /api/analysis/{name}.

숫자는 만들지 않는다 — 요청을 파싱해 analysis.run_analysis 로 넘기고 결과 JSON 을 낸다.
세그먼트 축은 반복 쿼리(?os=android&os=ios), 파라미터는 그 밖의 쿼리다.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from analytics.analyses.base import UnknownAnalysisError
from dashboard import filters, params
from api import analysis, cube_store, meta

app = FastAPI(title="Markov 대시보드 API")

# 사내망 개발용. vite dev proxy 를 쓰면 동일 출처라 실제로는 불필요하나, 직접 호출도 열어둔다.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/meta")
def get_meta():
    return meta.build_meta()


@app.get("/api/analysis/{name}")
def get_analysis_result(name: str, request: Request, start: str, end: str):
    # 세그먼트 축은 반복 쿼리로 받는다(multiselect).
    segment = {"services": meta.SERVICES, "dates": [start, end]}
    for axis in filters.SEGMENT_AXES:
        values = request.query_params.getlist(axis)
        if values:
            segment[axis] = values

    # 나머지 쿼리는 분석 파라미터.
    reserved = {"start", "end"} | set(filters.SEGMENT_AXES)
    param_values = {k: v for k, v in request.query_params.items() if k not in reserved}

    missing = [n for n in params.required_names(name) if n not in param_values]
    if missing:
        raise HTTPException(400, f"필수 파라미터를 선택하세요: {', '.join(missing)}")

    try:
        return analysis.run_analysis(
            name, start, end, segment, param_values, meta.STATE_DICT_VERSION)
    except cube_store.PeriodTooLongError as exc:
        raise HTTPException(400, str(exc)) from exc
    except UnknownAnalysisError as exc:
        raise HTTPException(404, str(exc)) from exc

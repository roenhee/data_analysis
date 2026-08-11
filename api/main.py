"""FastAPI 앱: /api/meta, /api/analysis/{name}.

숫자는 만들지 않는다 — 요청을 파싱해 analysis.run_analysis 로 넘기고 결과 JSON 을 낸다.
세그먼트 축은 반복 쿼리(?os=android&os=ios), 파라미터는 그 밖의 쿼리다.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from analytics.analyses.base import UnknownAnalysisError
from api import filters, params
from api import analysis, compare, cube_store, meta

app = FastAPI(title="Markov 대시보드 API")

# 사내망 개발용. vite dev proxy 를 쓰면 동일 출처라 실제로는 불필요하나, 직접 호출도 열어둔다.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/meta")
def get_meta():
    """분석 카탈로그·세그먼트 축·present_dates 메타를 낸다."""
    return meta.build_meta()


@app.get("/api/analysis/{name}")
def get_analysis_result(name: str, request: Request, start: str, end: str):
    """쿼리를 파싱해 run_analysis 로 넘기고 결과 JSON 을 낸다."""
    # 세그먼트 축은 반복 쿼리로 받는다(multiselect).
    segment = {"services": meta.SERVICES, "dates": [start, end]}
    for axis in filters.SEGMENT_AXES:
        values = request.query_params.getlist(axis)
        if values:
            segment[axis] = values

    # 나머지 쿼리는 분석 파라미터. page/page_size 는 서버 페이지네이션용이라 뺀다.
    reserved = {"start", "end", "page", "page_size"} | set(filters.SEGMENT_AXES)
    param_values = {k: v for k, v in request.query_params.items() if k not in reserved}
    page = int(request.query_params.get("page") or "1")
    _ps = request.query_params.get("page_size")
    page_size = int(_ps) if _ps else None

    missing = [n for n in params.required_names(name) if n not in param_values]
    if missing:
        raise HTTPException(400, f"필수 파라미터를 선택하세요: {', '.join(missing)}")

    try:
        return analysis.run_analysis(
            name, start, end, segment, param_values, meta.STATE_DICT_VERSION,
            page=page, page_size=page_size)
    except UnknownAnalysisError as exc:
        # KeyError 하위 클래스라 ValueError 와 겹치지 않는다 — 순서와 무관하게 안전하지만,
        # "모르는 분석"이 항상 404 로 남는다는 걸 명시하려고 먼저 둔다.
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        # 잘못된 클라이언트 입력(기간 역전·기간 상한 초과·날짜 형식 오류·파라미터 타입
        # 오류)은 전부 ValueError 로 올라온다 — 400 으로 매핑한다(500 이 아니다).
        # PeriodTooLongError 도 ValueError 하위 클래스라 여기 걸린다.
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/compare/{name}")
def get_compare_result(name: str, request: Request, start: str, end: str,
                       on: str, a: str, b: str):
    """`on` 축의 두 값(a·b)을 비교한다. on 은 세그먼트 축, a·b 는 그 값."""
    segment = {"services": meta.SERVICES, "dates": [start, end]}
    for axis in filters.SEGMENT_AXES:
        values = request.query_params.getlist(axis)
        if values:
            segment[axis] = values

    reserved = {"start", "end", "on", "a", "b"} | set(filters.SEGMENT_AXES)
    param_values = {k: v for k, v in request.query_params.items() if k not in reserved}

    missing = [n for n in params.required_names(name) if n not in param_values]
    if missing:
        raise HTTPException(400, f"필수 파라미터를 선택하세요: {', '.join(missing)}")

    try:
        return compare.run_compare(
            name, start, end, segment, on, a, b, param_values,
            meta.STATE_DICT_VERSION)
    except UnknownAnalysisError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

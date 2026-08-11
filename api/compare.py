"""비교 모드: `on` 축의 두 값(A·B)을 견줘 JSON 으로 낸다.

숫자는 `analytics.analyses.operators.compare` 가 만든다 — 여기선 cube_store 로드 + 다른 축
필터 + 직렬화만 한다. compare 가 돌려주는 `Comparison.result` 는 AnalysisResult 라
`analysis.result_to_json` 을 그대로 재사용한다(headline=pooled 델타, rows=날짜별 델타).
"""
from __future__ import annotations

from analytics.analyses import operators
from analytics.metrics.load import load_releases
from api import analysis, cube_store, filters, params


def run_compare(
    name: str, start: str, end: str, segment: dict,
    on: str, a: str, b: str, param_values: dict, state_dict_version: str,
) -> dict:
    """cube_store 로드 → (on 제외) 축 필터 → compare → JSON + compare 블록."""
    cubes = cube_store.load(
        tuple(sorted(filters.cube_names_for(name))),
        start, end, tuple(segment["services"]), state_dict_version,
    )
    # `on` 축은 compare 가 내부에서 A·B 로 가른다 — 나머지 축만 미리 좁힌다.
    other = {k: v for k, v in segment.items() if k != on}
    cubes = filters.apply_segment(cubes, other)

    call_params = params.coerce(name, param_values)
    # 앱 버전 비교만 배포일 컷오프가 필요하다(배포 전은 다른 모집단). 다른 축은 released=None.
    released = load_releases() if on == "app_version" else None
    comparison = operators.compare(
        cubes, name, on=on, a=a, b=b, released=released, **call_params
    )

    out = analysis.result_to_json(
        comparison.result, period_days_value=cube_store.period_days(start, end)
    )
    out["compare"] = {
        "on": on, "a": a, "b": b,
        "weight_skew": float(comparison.weight_skew),
        "date_reason": comparison.date_reason,
        "sign_disagrees": bool(comparison.sign_disagrees),
        "dates_used": list(comparison.dates_used),
    }
    return out

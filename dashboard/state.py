"""대시보드 상태 ↔ URL query params. 순수 함수 — Streamlit 을 모른다.

상태는 flat dict 다. 리스트(services)는 콤마, 날짜 범위(dates)는 콜론, 분석 파라미터는
`p_` 접두어로 인코딩한다. 알 수 없는 키는 디코딩에서 버려 손댄 URL 이 화면을 깨지 않는다.
"""
from __future__ import annotations

DEFAULTS: dict = {
    "mode": "single",
    "tab": "overview",
    "analysis": "session_trend",
    "dates": [],          # [] 이면 present_dates 전체 (filters 에서 채움)
    "services": [],       # [] 이면 빌드된 전체
    "service_type": [],   # [] 이면 전체 (필터 안 함). 다중 선택이라 리스트다.
    "app_version": [],
    "os": [],
    "gender": [],
    "age_band": [],
    "daypart": [],
    "params": {},         # 분석별 파라미터
    "page": 0,
}

_LIST_KEYS = ("services", "service_type", "app_version", "os", "gender",
              "age_band", "daypart")
_RANGE_KEYS = ("dates",)
_INT_KEYS = ("page",)


def encode_state(state: dict) -> dict[str, str]:
    """상태 dict → query param 문자열 dict."""
    out: dict[str, str] = {}
    for key, default in DEFAULTS.items():
        if key == "params":
            for name, value in state.get("params", {}).items():
                out[f"p_{name}"] = str(value)
            continue
        value = state.get(key, default)
        if key in _LIST_KEYS or key in _RANGE_KEYS:
            sep = "," if key in _LIST_KEYS else ":"
            out[key] = sep.join(map(str, value))
        else:
            out[key] = str(value)
    return out


def decode_state(params: dict) -> dict:
    """query param dict → 상태 dict. 기본값을 채우고 타입을 복원한다."""
    state = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    state["params"] = {}
    for key, raw in params.items():
        if key.startswith("p_"):
            state["params"][key[2:]] = _coerce_param(raw)
        elif key in _LIST_KEYS:
            state[key] = [s for s in raw.split(",") if s]
        elif key in _RANGE_KEYS:
            state[key] = [s for s in raw.split(":") if s]
        elif key in _INT_KEYS:
            state[key] = int(raw)
        elif key in DEFAULTS:
            state[key] = raw
        # 그 외 낯선 키는 무시
    return state


def _coerce_param(raw: str):
    """파라미터 문자열을 int 로 되돌릴 수 있으면 되돌린다(예: n=4)."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw

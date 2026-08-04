"""AnalysisResult 를 화면 조각으로 바꾸는 순수 변환. Streamlit 을 모른다."""
from __future__ import annotations

import math

import pandas as pd


def headline_cards(headline: dict) -> list[tuple[str, str]]:
    """{키: float} → [(라벨, 표시문자열)]. NaN 은 건너뛴다."""
    cards = []
    for key, value in headline.items():
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        cards.append((key, _fmt(value)))
    return cards


def _fmt(value: float) -> str:
    """정수 같은 큰 수는 천단위 콤마, 소수는 2자리. 무한대는 ∞ 로."""
    if math.isinf(value):
        return "∞" if value > 0 else "-∞"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:.2f}"


def table_slice(frame: pd.DataFrame, top: int) -> pd.DataFrame:
    """상위 top 행. 0 이하면 빈 프레임, 프레임보다 크면 전체."""
    return frame.head(max(0, top))


def envelope_summary(envelope: dict) -> dict:
    """봉투에서 화면에 낼 핵심만 뽑는다."""
    return {
        "warnings": [w.get("check_name", "?") for w in envelope.get("warnings", [])],
        "coverage": envelope.get("coverage", {}),
        "state_dict_version": envelope.get("state_dict_version", "?"),
        "n_dates": len(envelope.get("present_dates", [])),
    }

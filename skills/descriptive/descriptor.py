from __future__ import annotations

from data_layer.config import Config
from data_layer.skills_registry import register_skill

DESCRIPTOR = {
    "name": "descriptive",
    "description": "on-demand 절대(전수) 기술통계: 기간별 UV/PV·세션 engagement",
    "invocation": "run_analysis(config, source, analysis_type, params, run_id, config_version)",
    "expected_params": {
        "analysis_type": ["uv_pv_by_period", "session_engagement_by_period"],
        "window": "[start, end]",
        "grain": ["day", "week", "month"],
        "breakdown": ["app_version", "os", "service_code"],
        "filters": "{column: value}",
    },
}


def register(config: Config) -> None:
    """디스크립티브 스킬 디스크립터를 레지스트리에 upsert (③ 카탈로그용)."""
    register_skill(config, DESCRIPTOR)

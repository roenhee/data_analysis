"""이름 붙은 분석과 연산자. 숫자를 만드는 유일한 층."""
from analytics.analyses.base import (
    AnalysisResult,
    CubeSet,
    IncompleteEnvelopeError,
    UnknownAnalysisError,
    analysis,
    get_analysis,
    list_analyses,
    publish,
)

# 레지스트리는 임포트 시점에 채워진다. 분석 모듈을 여기서 끌어와야 `get_analysis` 가
# 이름으로 찾을 수 있다 — 소비자가 어느 모듈에 있는지 알아야 하면 레지스트리가 무의미하다.
from analytics.analyses import (  # noqa: E402,F401  (등록 부작용)
    descriptive,
    flow,
    quality,
)

__all__ = [
    "AnalysisResult",
    "CubeSet",
    "IncompleteEnvelopeError",
    "UnknownAnalysisError",
    "analysis",
    "get_analysis",
    "list_analyses",
    "publish",
]

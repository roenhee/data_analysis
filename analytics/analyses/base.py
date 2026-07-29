"""분석의 공통 타입과 발행 규약.

**숫자를 만드는 코드는 이 층뿐이다.** Claude 도 대시보드도 여기를 통과하므로 두 경로가
다른 답을 낼 수 없다. 탐색은 자유롭되 발행되지 않는다 — 발행하려면 분석으로 코드화한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from data_layer.config import Config
from data_layer.results import publish_result

# 봉투에 반드시 있어야 하는 것. 하나라도 빠지면 발행을 거부한다 —
# 커버리지 57% 짜리 체류가 전수로 읽히는 것을 막는 유일한 장치다.
REQUIRED_ENVELOPE_KEYS = (
    "state_dict_version", "services", "requested_dates", "present_dates",
    "missing_dates", "is_complete", "coverage", "warnings",
)


class IncompleteEnvelopeError(ValueError):
    """봉투 필수 항목이 빠진 채 발행하려 했다."""


class UnknownAnalysisError(KeyError):
    """레지스트리에 없는 분석 이름."""


@dataclass(frozen=True)
class CubeSet:
    """분석이 받는 큐브 묶음. 없는 큐브는 `None` 이다."""

    session: pd.DataFrame | None
    transition: pd.DataFrame | None
    quality: pd.DataFrame | None
    state_dict_version: str
    services: list[str]
    requested_dates: list[str]
    present_dates: list[str]

    def filter(self, dates: list[str] | None = None, **segment) -> "CubeSet":
        """날짜·축으로 좁힌 새 `CubeSet`. 연산자가 세그먼트를 가를 때 쓴다.

        큐브마다 컬럼이 다르므로(전이 큐브엔 `uv` 가 없다) 없는 컬럼 조건은 건너뛴다.
        """
        def cut(df):
            if df is None:
                return None
            out = df
            if dates is not None and "period" in out.columns:
                out = out[out["period"].isin(dates)]
            for col, want in segment.items():
                if col not in out.columns:
                    continue
                wants = want if isinstance(want, (list, tuple, set)) else [want]
                out = out[out[col].isin(list(wants))]
            return out

        return CubeSet(
            session=cut(self.session),
            transition=cut(self.transition),
            quality=cut(self.quality),
            state_dict_version=self.state_dict_version,
            services=list(self.services),
            requested_dates=list(self.requested_dates),
            present_dates=list(dates) if dates is not None else list(self.present_dates),
        )


@dataclass(frozen=True)
class AnalysisResult:
    """분석 하나의 산출물.

    `headline` 은 연산자가 델타를 낼 수 있는 **스칼라**들이다. 프레임 모양은 분석마다
    다르지만 headline 은 항상 `{이름: 수}` 라 `compare` 가 분석 종류를 안 가린다.

    `compare_key` 를 주면 연산자가 그 컬럼으로 행끼리 조인해 행별 델타도 낸다.
    """

    frame: pd.DataFrame
    headline: dict[str, float]
    envelope: dict
    compare_key: str | None = None
    viz: dict = field(default_factory=dict)


_REGISTRY: dict[str, Callable] = {}


def analysis(name: str):
    """이름 붙은 분석으로 등록한다. Claude·대시보드가 이 목록에서만 고른다."""
    def wrap(fn):
        _REGISTRY[name] = fn
        fn.analysis_name = name
        return fn
    return wrap


def list_analyses() -> list[str]:
    return sorted(_REGISTRY)


def get_analysis(name: str) -> Callable:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownAnalysisError(
            f"no analysis named {name!r}; known: {', '.join(list_analyses())}"
        ) from None


def publish(
    config: Config,
    result: AnalysisResult,
    run_id: str,
    analysis_type: str,
    title: str,
    insight: str | None = None,
) -> str:
    """봉투를 검사하고 ②↔③ 계약 형식으로 발행한다.

    같은 `(run_id, analysis_type, title)` 은 같은 id 라 덮어쓴다 — 대시보드가 같은
    세그먼트를 열 번 봐도 발행물은 하나다.
    """
    missing = [k for k in REQUIRED_ENVELOPE_KEYS if k not in result.envelope]
    if missing:
        raise IncompleteEnvelopeError(
            f"envelope is missing {', '.join(missing)}; a result without coverage and "
            "the dictionary version reads as full-population when it is not"
        )
    return publish_result(
        config=config,
        run_id=run_id,
        skill="basic-analysis",
        analysis_type=analysis_type,
        title=title,
        data=result.frame,
        viz={**result.viz, "headline": result.headline},
        params={"envelope": result.envelope},
        config_version=result.envelope["state_dict_version"],
        insight=insight,
        caveats=_caveats(result.envelope),
    )


def _caveats(envelope: dict) -> str:
    """봉투에서 사람이 읽을 주의사항을 만든다."""
    bits = [f"서비스 범위 {', '.join(envelope['services']) or '(없음)'}"]
    if not envelope.get("is_complete", True):
        bits.append(f"미빌드 날짜 {len(envelope['missing_dates'])}일")
    for name, value in sorted(envelope.get("coverage", {}).items()):
        bits.append(f"{name} 커버리지 {value:.1%}")
    if envelope.get("warnings"):
        bits.append(f"품질 경고 {len(envelope['warnings'])}건")
    return " · ".join(bits)

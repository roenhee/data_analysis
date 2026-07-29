"""분석의 공통 타입과 발행 규약.

**숫자를 만드는 코드는 이 층뿐이다.** Claude 도 대시보드도 여기를 통과하므로 두 경로가
다른 답을 낼 수 없다. 탐색은 자유롭되 발행되지 않는다 — 발행하려면 분석으로 코드화한다.
"""
from __future__ import annotations

import functools
import inspect
import json
from dataclasses import dataclass, field, replace
from typing import Callable

import pandas as pd

from data_layer.config import Config
from data_layer.results import publish_result, result_id

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


class ConflictingPublicationError(ValueError):
    """같은 제목으로 **다른 파라미터**의 결과를 발행하려 했다."""


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

    `params` 는 이 결과를 만든 호출 파라미터다. `@analysis` 가 채우므로 분석이 직접
    적을 필요는 없다 — 적으면 그쪽이 이긴다.
    """

    frame: pd.DataFrame
    headline: dict[str, float]
    envelope: dict
    compare_key: str | None = None
    viz: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)


def envelope_for(
    cubes: CubeSet, coverage: dict, warnings: list[dict] | None = None
) -> dict:
    """`CubeSet` 의 날짜 장부로 봉투를 만든다.

    분석마다 손으로 짜면 한 곳은 반드시 키를 빠뜨리고, 그 결과는 `publish` 에서야
    막힌다. 커버리지와 경고만 분석이 채운다 — 나머지는 큐브가 이미 알고 있다.
    """
    present = set(cubes.present_dates)
    missing = [d for d in cubes.requested_dates if d not in present]
    return {
        "state_dict_version": cubes.state_dict_version,
        "services": list(cubes.services),
        "requested_dates": list(cubes.requested_dates),
        "present_dates": list(cubes.present_dates),
        "missing_dates": missing,
        "is_complete": not missing,
        "coverage": dict(coverage),
        "warnings": list(warnings or []),
    }


_REGISTRY: dict[str, Callable] = {}


def _canonical(value):
    """발행물에 실을 안정적인 형태로 바꾼다.

    **집합은 정렬한다.** `repr` 순서가 프로세스마다 다르므로(문자열 해시 무작위화)
    그대로 기록하면 같은 호출이 실행마다 다른 파라미터로 남고, 재발행이 거짓 충돌로
    거부된다. 튜플·리스트도 JSON 이 리스트로 만드니 미리 맞춰 둔다.
    """
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(),
                                                        key=lambda kv: str(kv[0]))}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _called_with(fn: Callable, cubes, params: dict) -> dict:
    """호출에 쓰인 파라미터 전부. **기본값도 포함한다.**

    기본값을 빼면 나중에 기본값이 바뀌었을 때 옛 발행물의 숫자를 재현할 수 없고, 발행물만
    보고는 그게 바뀐 줄도 모른다. 큐브 인자와 `**_` 는 파라미터가 아니라 뺀다.
    """
    signature = inspect.signature(fn)
    bound = signature.bind(cubes, **params)
    bound.apply_defaults()
    variadic = {
        name for name, p in signature.parameters.items()
        if p.kind in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
    }
    first = next(iter(signature.parameters), None)
    return {
        key: _canonical(value) for key, value in bound.arguments.items()
        if key != first and key not in variadic
    }


def analysis(name: str):
    """이름 붙은 분석으로 등록한다. Claude·대시보드가 이 목록에서만 고른다.

    호출 파라미터를 결과에 기록한다 — 분석마다 손으로 적게 하면 하나는 빠뜨리고, 그
    누락은 조용하다. 가드를 연산자 한 곳에 모은 것과 같은 이유다.
    """
    def wrap(fn):
        @functools.wraps(fn)
        def called(cubes, **params):
            result = fn(cubes, **params)
            recorded = _called_with(fn, cubes, params)
            return replace(result, params={**recorded, **result.params})

        called.analysis_name = name
        _REGISTRY[name] = called
        return called
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
    _refuse_a_conflicting_overwrite(config, result, run_id, analysis_type, title)
    return publish_result(
        config=config,
        run_id=run_id,
        skill="basic-analysis",
        analysis_type=analysis_type,
        title=title,
        data=result.frame,
        viz={**result.viz, "headline": result.headline},
        params={"envelope": result.envelope, "analysis": result.params},
        config_version=result.envelope["state_dict_version"],
        insight=insight,
        caveats=_caveats(result.envelope),
    )


def _refuse_a_conflicting_overwrite(
    config: Config, result: AnalysisResult, run_id: str, analysis_type: str, title: str
) -> None:
    """같은 제목으로 다른 파라미터의 결과를 발행하려 하면 막는다.

    id 는 `(run_id, analysis_type, title)` 로만 정해진다 — 그래야 대시보드가 같은
    세그먼트를 열 번 봐도 발행물이 하나다. 그 대가로 **파라미터가 다르면 조용히 덮어써진다.**
    발행물 하나가 두 계산을 가리키게 되므로, 같은 호출을 다시 발행하는 것만 허용한다.
    """
    path = config.results_dir / f"{result_id(run_id, analysis_type, title)}.json"
    if not path.exists():
        return
    previous = json.loads(path.read_text()).get("params", {}).get("analysis")
    current = _canonical(result.params)
    if previous is None or previous == current:
        return
    differing = sorted(
        set(previous) ^ set(current)
        | {k for k in set(previous) & set(current) if previous[k] != current[k]}
    )
    raise ConflictingPublicationError(
        f"{title!r} in run {run_id!r} was already published with different analysis "
        f"parameters ({', '.join(differing)}); the id is derived from the title alone, "
        "so publishing this would overwrite a different computation — give it a title "
        "that says which parameters it used"
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

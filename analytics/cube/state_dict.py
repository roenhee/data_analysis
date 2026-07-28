"""state 사전: 큐브 빌드 전에 확정해 고정하는 값 목록.

화면·클릭레이어·앱버전의 채택 목록을 담는다. 날짜별 큐브 빌드는 이 사전을 고정한 채
수행되므로, 나중에 날짜를 추가해도 앞선 날짜의 state 집합이 흔들리지 않는다.
버전 비교 시에는 비교 대상 기간·버전을 합쳐 사전을 한 번만 만든다.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from data_layer.config import Config
from data_layer.util import content_hash

DEFAULT_CUT_RATIO = 0.95
DEFAULT_MIN_COUNT = 10_000


def apply_cut(counts: pd.DataFrame, cut_ratio: float, min_count: int) -> list[str]:
    """건수 내림차순으로 누적 커버리지 `cut_ratio` 까지 채택. `min_count` 미만은 제외.

    `counts` 는 `value`, `cnt` 두 컬럼을 갖는다.
    """
    if counts.empty:
        return []
    ordered = counts.sort_values("cnt", ascending=False, kind="mergesort")
    total = ordered["cnt"].sum()
    if total <= 0:
        return []
    cumulative = ordered["cnt"].cumsum()
    # 컷 경계에 걸친 값은 포함한다(누적이 처음 비율을 넘는 지점까지).
    within = cumulative.shift(fill_value=0) < cut_ratio * total
    kept = ordered[within & (ordered["cnt"] >= min_count)]
    return [str(v) for v in kept["value"].tolist()]


@dataclass(frozen=True)
class StateDict:
    screens: list[str]
    layer1: list[str]
    layer2: list[str]
    app_versions: list[str]
    cut_ratio: float = DEFAULT_CUT_RATIO
    min_count: int = DEFAULT_MIN_COUNT

    def version(self) -> str:
        return "sd_" + content_hash(
            self.screens,
            self.layer1,
            self.layer2,
            self.app_versions,
            self.cut_ratio,
            self.min_count,
        )


def _dir(config: Config) -> Path:
    return config.root / "state_dicts"


def save_state_dict(config: Config, sd: StateDict) -> Path:
    d = _dir(config)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{sd.version()}.json"
    payload = asdict(sd) | {"version": sd.version()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def load_state_dict(config: Config, version: str) -> StateDict:
    path = _dir(config) / f"{version}.json"
    raw = json.loads(path.read_text())
    raw.pop("version", None)
    return StateDict(**raw)

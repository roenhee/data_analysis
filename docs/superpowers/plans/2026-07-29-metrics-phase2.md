# 지표 계산 2단계 (기술통계 + 마르코프) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 1단계가 만든 큐브를 읽어 세그먼트별 기술통계(UV·PV·세션·체류)와 마르코프
지표(P행렬·이탈확률·stationary·expected steps·absorption·PMI)를 내는 순수 함수 층을
만든다.

**Architecture:** `analytics/metrics/` 는 **DB를 모른다.** 입력은 큐브 DataFrame, 출력은
지표 DataFrame인 순수 함수다. Trino 없이 손으로 만든 작은 큐브로 전부 검증할 수 있어야
한다 — 마르코프 수식 버그는 예외를 던지지 않고 **그럴듯한 숫자**를 내므로 이 격리가
필수다. 큐브 로딩과 부분 빌드 감지는 `load.py` 한 곳에 모으고, 수식 모듈은 프레임만
받는다.

**Tech Stack:** Python 3.14, pandas, numpy, pytest. DuckDB는 `store.read_cube` 안에서만
쓰인다.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `analytics/metrics/__init__.py` | 공개 함수 재수출 |
| `analytics/metrics/load.py` | 큐브 로딩 + **부분 빌드 감지**. 여기만 `config`·파일시스템을 안다 |
| `analytics/metrics/frame.py` | 롤업 행 규약, 세그먼트 필터, `uv` 합산 차단 |
| `analytics/metrics/markov.py` | P행렬·이탈확률·stationary·expected steps·absorption·PMI |
| `analytics/metrics/descriptive.py` | UV·PV·세션·체류 |
| `analytics/metrics/envelope.py` | 결과 봉투(커버리지·품질경고·사전버전) |
| `tests/analytics/metrics/test_*.py` | 위 각각 |

`markov.py`·`descriptive.py`·`frame.py` 는 `config` 도 파일시스템도 임포트하지 않는다.
이 규칙은 Task 2에서 테스트로 고정한다.

---

## 1단계에서 넘어온 제약 (전부 실측으로 확인된 것)

이 다섯 가지는 협상 대상이 아니다. 어기면 조용히 틀린 숫자가 나온다.

**① 세션 큐브에는 롤업 행이 섞여 있다.** `GROUPING SETS` 로 만들어져서 전체 조합 행 +
축 하나씩 접은 행 + `(period)` + `()` 가 한 파일에 있다. 접힌 축은 **NULL** 이다.
필터 없이 `sessions.sum()` 을 하면 같은 세션을 9번 넘게 센다. 전이·품질 큐브는 평범한
`GROUP BY` 라 롤업 행이 없다.

**② `uv` 는 가산이 아니다.** 롤업은 큐브에 이미 있다. 직접 합산하면 부풀어 오른다.

**③ 체류는 두 가지고 정의가 다르다.**
- `session` 큐브의 `duration_sum`: 세션 span(`date_diff` 초), 커버리지 100%
- `transition` 큐브의 `dur_sum`: `UsagePage` 기반, **커버리지 57~69%**

전자는 전수, 후자는 아니다. 후자는 반드시 `dur_sum / dur_n` 으로 나눈다.
`dur_sum / cnt` 는 커버리지만큼 축소된 **틀린 값**이다.

**④ `read_cube` 는 일부 날짜가 없어도 조용히 읽는다.** 30일을 요청해 3일을 받은 호출자는
아무 신호 없이 틀린 분모로 계산한다. 비율·평균·확률을 내기 전에 **요청 날짜와 실제
읽힌 날짜를 반드시 대조**한다. 스펙이 "권고가 아니라 요건"이라고 못박은 항목이다.

**⑤ 서비스 목록은 축이 아니라 범위다.** 세션의 44.7%가 여러 서비스에 걸쳐서
`service_code` 를 세션 큐브 축으로 넣을 수 없다. 세션 지표의 서비스 범위는 그 큐브가
어떤 `services` 로 빌드됐는지에 달렸고, 큐브에는 그 정보가 없다. 봉투(Task 9)에 담는다.

---

### Task 1: `metrics/` 패키지와 부분 빌드 감지 로더

**Files:**
- Create: `analytics/metrics/__init__.py`
- Create: `analytics/metrics/load.py`
- Create: `tests/analytics/metrics/__init__.py`
- Create: `tests/analytics/metrics/test_load.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_load.py`:

```python
import pandas as pd
import pytest

from analytics.metrics.load import IncompleteCubeError, LoadedCube, load_cube

KEY = dict(
    source_version="sv1",
    state_dict_version="sd_abc",
    axes=("period", "os"),
    cube_name="session",
    sql_hash="lh_abc",
)


def _write(config, date, rows):
    from analytics.cube.store import write_cube
    write_cube(config, pd.DataFrame(rows), date=date, **KEY)


def test_loads_the_requested_dates(config):
    _write(config, "2026-07-26", {"sessions": [1]})
    _write(config, "2026-07-27", {"sessions": [2]})
    got = load_cube(config, dates=["2026-07-26", "2026-07-27"], **KEY)
    assert isinstance(got, LoadedCube)
    assert got.frame["sessions"].sum() == 3
    assert got.present_dates == ["2026-07-26", "2026-07-27"]
    assert got.missing_dates == []
    assert got.is_complete is True


def test_reports_missing_dates_instead_of_hiding_them(config):
    # read_cube 는 일부만 없으면 조용히 읽는다. 그 조용함이 여기서 끝나야 한다.
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-26", "2026-07-27"], **KEY)
    assert got.missing_dates == ["2026-07-27"]
    assert got.is_complete is False


def test_require_complete_raises_on_a_partial_build(config):
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-26", "2026-07-27"], **KEY)
    with pytest.raises(IncompleteCubeError, match="2026-07-27"):
        got.require_complete()


def test_require_complete_passes_when_every_date_is_present(config):
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-26"], **KEY)
    assert got.require_complete() is got


def test_missing_everything_still_raises_cube_not_built(config):
    from analytics.cube.store import CubeNotBuiltError
    with pytest.raises(CubeNotBuiltError):
        load_cube(config, dates=["2026-07-26"], **KEY)


def test_duplicate_dates_are_requested_once(config):
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-26", "2026-07-26"], **KEY)
    assert got.frame["sessions"].sum() == 1
    assert got.present_dates == ["2026-07-26"]


def test_dates_are_reported_in_sorted_order(config):
    _write(config, "2026-07-27", {"sessions": [1]})
    _write(config, "2026-07-26", {"sessions": [1]})
    got = load_cube(config, dates=["2026-07-27", "2026-07-26"], **KEY)
    assert got.present_dates == ["2026-07-26", "2026-07-27"]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_load.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.metrics'`

- [ ] **Step 3: 구현**

`analytics/metrics/__init__.py`:

```python
"""큐브 위에서 도는 지표 계산. Trino 에 접근하지 않는다."""
from analytics.metrics.load import IncompleteCubeError, LoadedCube, load_cube

__all__ = ["IncompleteCubeError", "LoadedCube", "load_cube"]
```

`analytics/metrics/load.py`:

```python
"""큐브 로딩과 부분 빌드 감지.

`metrics/` 에서 **파일시스템을 아는 유일한 모듈**이다. 수식 모듈은 프레임만 받는다.

`store.read_cube` 는 요청 날짜가 전부 없으면 예외를 내지만 **일부만 없으면 있는 것만
조용히 읽는다**(부분 빌드 상태에서도 읽을 수 있어야 하므로 의도된 동작이다). 그래서
30일을 요청해 3일을 받은 호출자는 아무 신호 없이 틀린 분모로 계산한다. 그 조용함을
여기서 끝낸다.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analytics.cube.store import has_cube, read_cube
from data_layer.config import Config


class IncompleteCubeError(RuntimeError):
    """요청한 날짜 중 일부가 빌드되지 않았다."""


@dataclass(frozen=True)
class LoadedCube:
    """읽은 프레임과 **무엇을 못 읽었는지**를 함께 들고 다닌다."""

    frame: pd.DataFrame
    requested_dates: list[str]
    present_dates: list[str]
    missing_dates: list[str]

    @property
    def is_complete(self) -> bool:
        return not self.missing_dates

    def require_complete(self) -> "LoadedCube":
        """비율·평균·확률을 내기 전에 호출한다. 스펙상 권고가 아니라 요건이다."""
        if self.missing_dates:
            raise IncompleteCubeError(
                f"{len(self.missing_dates)}/{len(self.requested_dates)} dates are "
                f"not built: {', '.join(self.missing_dates)}; build them first — "
                "computing a ratio over a partial window yields a plausible number "
                "with the wrong denominator"
            )
        return self


def load_cube(config: Config, dates: list[str], **key_parts) -> LoadedCube:
    """요청 날짜를 읽고 빠진 날짜를 함께 돌려준다."""
    requested = sorted(set(dates))
    present = [d for d in requested if has_cube(config, date=d, **key_parts)]
    missing = [d for d in requested if d not in present]
    frame = read_cube(config, dates=present or requested, **key_parts)
    return LoadedCube(
        frame=frame,
        requested_dates=requested,
        present_dates=present,
        missing_dates=missing,
    )
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_load.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics tests/analytics/metrics
git commit -m "feat: add the metrics cube loader with partial-build detection"
```

---

### Task 2: 롤업 행 규약과 `uv` 합산 차단

**Files:**
- Create: `analytics/metrics/frame.py`
- Create: `tests/analytics/metrics/test_frame.py`

세션 큐브는 `GROUPING SETS` 로 만들어져 **전체 조합 행과 롤업 행이 한 파일에 섞여**
있다. 접힌 축은 NULL 이다. 이걸 안 거르고 합산하면 같은 세션을 여러 번 센다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_frame.py`:

```python
import pandas as pd
import pytest

from analytics.metrics.frame import (
    NonAdditiveMeasureError,
    additive_sum,
    full_combination_rows,
    rollup_rows,
    select_segment,
)

AXES = ("period", "os", "gender")


def _cube() -> pd.DataFrame:
    """전체 조합 2행 + os 접은 롤업 1행 + 전체 롤업 1행."""
    return pd.DataFrame([
        {"period": "2026-07-27", "os": "android", "gender": "M", "sessions": 10, "uv": 8},
        {"period": "2026-07-27", "os": "ios", "gender": "M", "sessions": 5, "uv": 4},
        {"period": "2026-07-27", "os": None, "gender": "M", "sessions": 15, "uv": 11},
        {"period": None, "os": None, "gender": None, "sessions": 15, "uv": 11},
    ])


def test_full_combination_rows_drops_every_rollup_row():
    got = full_combination_rows(_cube(), AXES)
    assert len(got) == 2
    assert set(got["os"]) == {"android", "ios"}


def test_summing_the_raw_frame_would_double_count():
    # 이 테스트는 왜 필터가 필요한지 고정한다. 원본 합계는 실제의 2배다.
    raw = _cube()["sessions"].sum()
    filtered = full_combination_rows(_cube(), AXES)["sessions"].sum()
    assert raw == 45
    assert filtered == 15


def test_rollup_rows_selects_the_row_where_the_named_axes_are_folded():
    got = rollup_rows(_cube(), AXES, folded=("os",))
    assert len(got) == 1
    assert int(got.iloc[0]["uv"]) == 11


def test_rollup_rows_can_select_the_grand_total():
    got = rollup_rows(_cube(), AXES, folded=("period", "os", "gender"))
    assert len(got) == 1
    assert int(got.iloc[0]["sessions"]) == 15


def test_additive_sum_allows_additive_measures():
    rows = full_combination_rows(_cube(), AXES)
    assert additive_sum(rows, "sessions") == 15


def test_additive_sum_refuses_uv():
    # uv 는 큐브의 롤업 행에서 읽어야 한다. 합산하면 부풀어 오른다.
    rows = full_combination_rows(_cube(), AXES)
    with pytest.raises(NonAdditiveMeasureError, match="uv"):
        additive_sum(rows, "uv")


def test_select_segment_filters_by_equality():
    got = select_segment(full_combination_rows(_cube(), AXES), os="android")
    assert len(got) == 1
    assert int(got.iloc[0]["sessions"]) == 10


def test_select_segment_accepts_a_list_of_values():
    got = select_segment(full_combination_rows(_cube(), AXES), os=["android", "ios"])
    assert len(got) == 2


def test_select_segment_rejects_an_unknown_column():
    with pytest.raises(KeyError, match="nope"):
        select_segment(_cube(), nope="x")


def test_metrics_modules_do_not_import_the_filesystem():
    """`frame`·`markov`·`descriptive` 는 순수해야 한다.

    마르코프 수식 버그는 예외를 안 던지고 그럴듯한 숫자를 낸다. 손으로 만든 작은
    큐브로 검증할 수 있어야 하고, 그러려면 DB·config 의존이 없어야 한다.
    """
    import ast
    from pathlib import Path

    banned = {"data_layer.config", "analytics.cube.store", "duckdb", "os", "pathlib"}
    for name in ("frame", "markov", "descriptive"):
        path = Path("analytics/metrics") / f"{name}.py"
        if not path.exists():
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                mods = {node.module or ""}
            else:
                continue
            assert not (mods & banned), f"{name}.py imports {mods & banned}"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_frame.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.metrics.frame'`

- [ ] **Step 3: 구현**

`analytics/metrics/frame.py`:

```python
"""큐브 프레임 다루기. 파일시스템도 config 도 모르는 순수 모듈.

**세션 큐브에는 롤업 행이 섞여 있다.** `GROUPING SETS` 로 만들어져 전체 조합 행 +
축 하나씩 접은 행 + `(period)` + `()` 가 한 파일에 있고, 접힌 축은 NULL 이다.
필터 없이 합산하면 같은 세션을 여러 번 센다. 전이·품질 큐브는 평범한 `GROUP BY` 라
롤업 행이 없으므로 `full_combination_rows` 가 전체를 그대로 돌려준다.
"""
from __future__ import annotations

import pandas as pd

# 큐브에서 가산이 아닌 측정값. 롤업은 큐브에 이미 들어 있으므로 거기서 읽는다.
NON_ADDITIVE = ("uv",)


class NonAdditiveMeasureError(ValueError):
    """가산이 아닌 측정값을 합산하려 했다."""


def full_combination_rows(df: pd.DataFrame, axes: tuple[str, ...]) -> pd.DataFrame:
    """축이 하나도 접히지 않은 행만 남긴다."""
    present = [a for a in axes if a in df.columns]
    if not present:
        return df
    return df.dropna(subset=present)


def rollup_rows(
    df: pd.DataFrame, axes: tuple[str, ...], folded: tuple[str, ...]
) -> pd.DataFrame:
    """`folded` 축이 정확히 접힌 롤업 행만 남긴다."""
    unknown = set(folded) - set(axes)
    if unknown:
        raise KeyError(f"not an axis: {sorted(unknown)}")
    out = df
    for axis in axes:
        if axis not in out.columns:
            continue
        if axis in folded:
            out = out[out[axis].isna()]
        else:
            out = out[out[axis].notna()]
    return out


def select_segment(df: pd.DataFrame, **filters) -> pd.DataFrame:
    """축 값으로 세그먼트를 고른다. 값 하나 또는 목록."""
    out = df
    for column, wanted in filters.items():
        if column not in out.columns:
            raise KeyError(f"no such column: {column!r}")
        if isinstance(wanted, (list, tuple, set)):
            out = out[out[column].isin(list(wanted))]
        else:
            out = out[out[column] == wanted]
    return out


def additive_sum(df: pd.DataFrame, measure: str) -> float:
    """가산 측정값을 합산한다. 비가산이면 거부한다."""
    if measure in NON_ADDITIVE:
        raise NonAdditiveMeasureError(
            f"{measure!r} is not additive — the same user counted on two days is one "
            "user, not two; read the pre-computed rollup row from the cube instead "
            "(see rollup_rows)"
        )
    return float(df[measure].sum())
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_frame.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/frame.py tests/analytics/metrics/test_frame.py
git commit -m "feat: add rollup-row selection and non-additive measure guard"
```

---

### Task 3: 전이행렬 P

**Files:**
- Create: `analytics/metrics/markov.py`
- Create: `tests/analytics/metrics/test_markov_matrix.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_markov_matrix.py`:

```python
import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import EXIT, START, TransitionMatrix, transition_matrix


def _edges(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


def test_rows_sum_to_one():
    P = transition_matrix(_edges([("A", "B", 3), ("A", "C", 1), ("B", "C", 2)]))
    assert np.allclose(P.matrix.sum(axis=1), 1.0)


def test_probabilities_are_counts_over_the_row_total():
    P = transition_matrix(_edges([("A", "B", 3), ("A", "C", 1)]))
    assert P.probability("A", "B") == pytest.approx(0.75)
    assert P.probability("A", "C") == pytest.approx(0.25)


def test_states_are_sorted_with_start_first_and_exit_last():
    P = transition_matrix(_edges([(START, "B", 1), ("B", EXIT, 1), ("B", "A", 1)]))
    assert P.states == [START, "A", "B", EXIT]


def test_exit_is_absorbing():
    P = transition_matrix(_edges([("A", EXIT, 1)]))
    assert P.probability(EXIT, EXIT) == pytest.approx(1.0)


def test_a_state_with_no_outgoing_edges_gets_a_self_loop():
    # 행 합이 1이 아니면 뒤의 모든 계산이 조용히 틀린다.
    P = transition_matrix(_edges([("A", "B", 1)]))
    assert P.probability("B", "B") == pytest.approx(1.0)
    assert np.allclose(P.matrix.sum(axis=1), 1.0)


def test_duplicate_edges_are_summed():
    P = transition_matrix(_edges([("A", "B", 1), ("A", "B", 3)]))
    assert P.count("A", "B") == 4


def test_zero_count_edges_do_not_create_states():
    P = transition_matrix(_edges([("A", "B", 1), ("C", "D", 0)]))
    assert "C" not in P.states


def test_empty_frame_is_rejected_rather_than_returning_an_empty_matrix():
    with pytest.raises(ValueError, match="no transitions"):
        transition_matrix(_edges([]))


def test_unknown_state_lookup_raises():
    P = transition_matrix(_edges([("A", "B", 1)]))
    with pytest.raises(KeyError, match="Z"):
        P.probability("Z", "A")


def test_matrix_is_a_plain_numpy_array_of_floats():
    P = transition_matrix(_edges([("A", "B", 1)]))
    assert isinstance(P.matrix, np.ndarray)
    assert P.matrix.dtype == np.float64
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_markov_matrix.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.metrics.markov'`

- [ ] **Step 3: 구현**

`analytics/metrics/markov.py`:

```python
"""마르코프 지표. 큐브 프레임만 받는 순수 함수다.

수식 버그는 예외를 던지지 않고 **그럴듯한 숫자**를 낸다. 그래서 이 모듈은 DB 를 모르고,
손으로 만든 2~3 상태 체인으로 해석적 정답과 대조할 수 있어야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

START = "START"
EXIT = "EXIT"


def _ordered_states(states: set[str]) -> list[str]:
    """START 먼저, EXIT 마지막, 나머지는 사전순. 행렬을 눈으로 읽을 수 있게 한다."""
    middle = sorted(s for s in states if s not in (START, EXIT))
    out = []
    if START in states:
        out.append(START)
    out.extend(middle)
    if EXIT in states:
        out.append(EXIT)
    return out


@dataclass(frozen=True)
class TransitionMatrix:
    """행 확률 행렬과 원본 카운트."""

    states: list[str]
    matrix: np.ndarray
    counts: np.ndarray

    def _index(self, state: str) -> int:
        try:
            return self.states.index(state)
        except ValueError:
            raise KeyError(f"unknown state: {state!r}") from None

    def probability(self, from_state: str, to_state: str) -> float:
        return float(self.matrix[self._index(from_state), self._index(to_state)])

    def count(self, from_state: str, to_state: str) -> float:
        return float(self.counts[self._index(from_state), self._index(to_state)])


def transition_matrix(edges: pd.DataFrame) -> TransitionMatrix:
    """`(from_state, to_state, cnt)` 프레임을 행 확률 행렬로.

    행 합은 반드시 1이다. 나가는 엣지가 없는 상태(EXIT 포함)는 자기 루프를 준다 —
    행 합이 1이 아니면 stationary·expected steps 가 전부 조용히 틀린다.
    """
    used = edges[edges["cnt"] > 0]
    if used.empty:
        raise ValueError("no transitions: the frame has no rows with cnt > 0")

    grouped = used.groupby(["from_state", "to_state"], as_index=False)["cnt"].sum()
    states = _ordered_states(
        set(grouped["from_state"]) | set(grouped["to_state"])
    )
    index = {s: i for i, s in enumerate(states)}

    counts = np.zeros((len(states), len(states)), dtype=np.float64)
    for row in grouped.itertuples():
        counts[index[row.from_state], index[row.to_state]] = float(row.cnt)

    totals = counts.sum(axis=1)
    matrix = np.zeros_like(counts)
    for i, total in enumerate(totals):
        if total > 0:
            matrix[i] = counts[i] / total
        else:
            matrix[i, i] = 1.0  # 흡수: 나가는 곳이 없다
    return TransitionMatrix(states=states, matrix=matrix, counts=counts)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_markov_matrix.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/markov.py tests/analytics/metrics/test_markov_matrix.py
git commit -m "feat: build the row-stochastic transition matrix"
```

---

### Task 4: 이탈확률과 stationary 분포

**Files:**
- Modify: `analytics/metrics/markov.py`
- Create: `tests/analytics/metrics/test_markov_stationary.py`

**stationary 는 화면 전용 부분체인에서 계산한다.** 전체 체인은 EXIT 가 흡수 상태라
정상분포가 전부 EXIT 에 몰린 자명한 답이 된다("결국 모두 나간다"). 알고 싶은 것은
"둘러보는 동안 어느 화면에 오래 머무는가" 이므로 START·EXIT 를 빼고 행을 재정규화한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_markov_stationary.py`:

```python
import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import (
    EXIT,
    START,
    exit_probabilities,
    stationary_distribution,
    transition_matrix,
)


def _edges(rows):
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


def test_exit_probability_is_the_share_of_departures_that_leave():
    P = transition_matrix(_edges([("A", "B", 3), ("A", EXIT, 1)]))
    got = exit_probabilities(P)
    assert got.loc[got["state"] == "A", "exit_prob"].iloc[0] == pytest.approx(0.25)


def test_exit_probability_omits_start_and_exit_themselves():
    P = transition_matrix(_edges([(START, "A", 1), ("A", EXIT, 1)]))
    assert set(exit_probabilities(P)["state"]) == {"A"}


def test_exit_probability_is_zero_when_nobody_leaves_from_there():
    P = transition_matrix(_edges([("A", "B", 1), ("B", EXIT, 1)]))
    got = exit_probabilities(P).set_index("state")["exit_prob"]
    assert got["A"] == pytest.approx(0.0)
    assert got["B"] == pytest.approx(1.0)


def test_stationary_sums_to_one():
    P = transition_matrix(_edges([("A", "B", 1), ("B", "A", 1), ("A", EXIT, 1)]))
    assert stationary_distribution(P)["pi"].sum() == pytest.approx(1.0)


def test_stationary_satisfies_pi_equals_pi_P():
    """불변식 π = πP. 화면 전용 부분체인 위에서 성립해야 한다."""
    P = transition_matrix(
        _edges([("A", "B", 3), ("A", "C", 1), ("B", "C", 2), ("C", "A", 4)])
    )
    got = stationary_distribution(P)
    states = list(got["state"])
    pi = got["pi"].to_numpy()
    idx = [P.states.index(s) for s in states]
    sub = P.matrix[np.ix_(idx, idx)]
    sub = sub / sub.sum(axis=1, keepdims=True)
    assert np.allclose(pi @ sub, pi, atol=1e-9)


def test_stationary_of_a_symmetric_two_state_chain_is_half_and_half():
    # 해석적 정답: A<->B 대칭이면 정상분포는 0.5/0.5.
    P = transition_matrix(_edges([("A", "B", 1), ("B", "A", 1)]))
    got = stationary_distribution(P).set_index("state")["pi"]
    assert got["A"] == pytest.approx(0.5)
    assert got["B"] == pytest.approx(0.5)


def test_stationary_of_a_biased_two_state_chain_matches_hand_calculation():
    # A->B 확률 1.0, B->A 확률 0.25, B->B 0.75.
    # π_A = 0.25/(1+0.25) = 0.2, π_B = 0.8
    P = transition_matrix(_edges([("A", "B", 4), ("B", "A", 1), ("B", "B", 3)]))
    got = stationary_distribution(P).set_index("state")["pi"]
    assert got["A"] == pytest.approx(0.2)
    assert got["B"] == pytest.approx(0.8)


def test_stationary_excludes_start_and_exit():
    P = transition_matrix(_edges([(START, "A", 1), ("A", "B", 1), ("B", EXIT, 1)]))
    assert START not in set(stationary_distribution(P)["state"])
    assert EXIT not in set(stationary_distribution(P)["state"])


def test_stationary_needs_at_least_one_screen_state():
    P = transition_matrix(_edges([(START, EXIT, 1)]))
    with pytest.raises(ValueError, match="no screen states"):
        stationary_distribution(P)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_markov_stationary.py -q`
Expected: FAIL — `ImportError: cannot import name 'exit_probabilities'`

- [ ] **Step 3: 구현 — `markov.py` 끝에 추가**

```python
def _screen_states(P: TransitionMatrix) -> list[str]:
    return [s for s in P.states if s not in (START, EXIT)]


def exit_probabilities(P: TransitionMatrix) -> pd.DataFrame:
    """화면별 "다음 걸음이 이탈일 확률". START·EXIT 자신은 제외한다."""
    screens = _screen_states(P)
    if EXIT not in P.states:
        return pd.DataFrame({"state": screens, "exit_prob": [0.0] * len(screens)})
    return pd.DataFrame(
        {
            "state": screens,
            "exit_prob": [P.probability(s, EXIT) for s in screens],
        }
    )


def stationary_distribution(P: TransitionMatrix) -> pd.DataFrame:
    """화면 전용 부분체인의 정상분포 π (π = πP, Σπ = 1).

    **START·EXIT 를 뺀 뒤 행을 재정규화한다.** 전체 체인은 EXIT 가 흡수 상태라
    정상분포가 전부 EXIT 에 몰린 자명한 답("결국 모두 나간다")이 되어 쓸모가 없다.
    알고 싶은 것은 둘러보는 동안의 화면 비중이다.
    """
    screens = _screen_states(P)
    if not screens:
        raise ValueError("no screen states: the chain is only START/EXIT")
    idx = [P.states.index(s) for s in screens]
    sub = P.matrix[np.ix_(idx, idx)].copy()

    totals = sub.sum(axis=1, keepdims=True)
    for i, total in enumerate(totals):
        if total[0] <= 0:
            sub[i, i] = 1.0  # 화면 밖으로만 나가는 상태: 자기 루프로 흡수
            totals[i] = 1.0
    sub = sub / totals

    # πP = π, Σπ = 1 을 선형계로 푼다. 고유벡터보다 수치적으로 안정적이다.
    n = len(screens)
    A = np.vstack([sub.T - np.eye(n), np.ones(n)])
    b = np.append(np.zeros(n), 1.0)
    pi, *_ = np.linalg.lstsq(A, b, rcond=None)
    return pd.DataFrame({"state": screens, "pi": pi})
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_markov_stationary.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/markov.py tests/analytics/metrics/test_markov_stationary.py
git commit -m "feat: add exit probability and the screen-only stationary distribution"
```

---

### Task 5: expected steps to exit 와 absorption 확률

**Files:**
- Modify: `analytics/metrics/markov.py`
- Create: `tests/analytics/metrics/test_markov_absorption.py`

흡수 마르코프 체인의 표준 결과를 쓴다. 전이 상태 부분행렬 `Q`, 기본행렬
`N = (I - Q)^-1` 일 때 상태 `i` 에서의 기대 걸음 수는 `N` 의 `i` 행 합이고,
흡수 상태별 도달 확률은 `B = N·R` 이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_markov_absorption.py`:

```python
import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import (
    EXIT,
    START,
    absorption_probabilities,
    expected_steps_to_exit,
    transition_matrix,
)


def _edges(rows):
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


def test_one_step_chain_takes_exactly_one_step():
    # A -> EXIT 확률 1. 해석적 정답 1.
    P = transition_matrix(_edges([("A", EXIT, 1)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert got["A"] == pytest.approx(1.0)


def test_two_step_chain_takes_exactly_two_steps():
    # A -> B -> EXIT, 모두 확률 1. 해석적 정답 A=2, B=1.
    P = transition_matrix(_edges([("A", "B", 1), ("B", EXIT, 1)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert got["A"] == pytest.approx(2.0)
    assert got["B"] == pytest.approx(1.0)


def test_geometric_chain_matches_the_closed_form():
    # A 에서 확률 0.25 로 EXIT, 0.75 로 자기 자신. 기대 걸음 = 1/0.25 = 4.
    P = transition_matrix(_edges([("A", EXIT, 1), ("A", "A", 3)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert got["A"] == pytest.approx(4.0)


def test_expected_steps_are_always_positive():
    P = transition_matrix(
        _edges([("A", "B", 3), ("B", "C", 2), ("C", EXIT, 1), ("C", "A", 1)])
    )
    assert (expected_steps_to_exit(P)["expected_steps"] > 0).all()


def test_expected_steps_omits_start_and_exit():
    P = transition_matrix(_edges([(START, "A", 1), ("A", EXIT, 1)]))
    assert set(expected_steps_to_exit(P)["state"]) == {"A"}


def test_a_state_that_can_never_reach_exit_is_reported_as_infinite():
    # A<->B 만 오가고 EXIT 로 가는 길이 없다. 조용히 큰 수를 내면 안 된다.
    P = transition_matrix(_edges([("A", "B", 1), ("B", "A", 1), ("C", EXIT, 1)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert np.isinf(got["A"])
    assert np.isinf(got["B"])
    assert got["C"] == pytest.approx(1.0)


def test_a_state_that_might_fall_into_a_dead_end_is_also_infinite():
    """EXIT 로 가는 길이 있어도 기대값은 발산할 수 있다.

    A 는 절반 확률로 EXIT, 절반 확률로 D 로 간다. D 는 자기 루프라 영영 못 나온다.
    "EXIT 도달 가능하니 유한"으로 처리하면 A 에 그럴듯한 유한값(여기선 2.0 근처)이
    나온다. 실제 기대 걸음 수는 무한이다 — 절반은 영영 안 끝난다.
    """
    P = transition_matrix(_edges([("A", EXIT, 1), ("A", "D", 1), ("D", "D", 1)]))
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert np.isinf(got["A"])
    assert np.isinf(got["D"])


def test_a_state_upstream_of_a_dead_end_is_infinite_too():
    # Z -> A -> (EXIT | D), D 는 막다른 곳. 오염은 상류로 전파된다.
    P = transition_matrix(
        _edges([("Z", "A", 1), ("A", EXIT, 1), ("A", "D", 1), ("D", "D", 1)])
    )
    got = expected_steps_to_exit(P).set_index("state")["expected_steps"]
    assert np.isinf(got["Z"])


def test_absorption_probabilities_sum_to_one_per_state():
    P = transition_matrix(
        _edges([("A", "GOAL", 1), ("A", EXIT, 3), ("GOAL", "GOAL", 1)])
    )
    got = absorption_probabilities(P, absorbing=("GOAL", EXIT))
    rows = got.set_index("state")
    assert rows.loc["A", ["GOAL", EXIT]].sum() == pytest.approx(1.0)


def test_absorption_probability_matches_hand_calculation():
    # A 에서 1/4 확률로 GOAL, 3/4 로 EXIT. 둘 다 흡수.
    P = transition_matrix(
        _edges([("A", "GOAL", 1), ("A", EXIT, 3), ("GOAL", "GOAL", 1)])
    )
    got = absorption_probabilities(P, absorbing=("GOAL", EXIT)).set_index("state")
    assert got.loc["A", "GOAL"] == pytest.approx(0.25)
    assert got.loc["A", EXIT] == pytest.approx(0.75)


def test_absorption_defaults_to_exit_only():
    P = transition_matrix(_edges([("A", "B", 1), ("B", EXIT, 1)]))
    got = absorption_probabilities(P)
    assert list(got.columns) == ["state", EXIT]
    assert got.set_index("state").loc["A", EXIT] == pytest.approx(1.0)


def test_absorption_rejects_a_state_that_is_not_in_the_chain():
    P = transition_matrix(_edges([("A", EXIT, 1)]))
    with pytest.raises(KeyError, match="NOPE"):
        absorption_probabilities(P, absorbing=("NOPE",))
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_markov_absorption.py -q`
Expected: FAIL — `ImportError: cannot import name 'expected_steps_to_exit'`

- [ ] **Step 3: 구현 — `markov.py` 끝에 추가**

```python
def _fundamental(P: TransitionMatrix, absorbing: tuple[str, ...]):
    """전이 상태 목록과 기본행렬 `N = (I - Q)^-1` 를 돌려준다. absorption 전용이다.

    흡수 집합에 절대 닿지 못하는 상태가 있으면 `I - Q` 가 특이행렬이 된다. 그때는
    `None` 을 돌려주고 호출자가 `NaN` 으로 표기한다 — 유사역행렬로 얼버무리면
    합이 1이 아닌 확률이 조용히 나온다.

    (`expected_steps_to_exit` 는 이걸 쓰지 않는다. 거기서는 특이행렬이 되기 **전에**
    오염된 상태를 걸러내야 하므로 별도 경로다.)
    """
    for state in absorbing:
        if state not in P.states:
            raise KeyError(f"unknown state: {state!r}")
    transient = [s for s in P.states if s not in absorbing and s != START]
    if not transient:
        return transient, None
    t_idx = [P.states.index(s) for s in transient]
    Q = P.matrix[np.ix_(t_idx, t_idx)]
    I = np.eye(len(transient))
    try:
        N = np.linalg.inv(I - Q)
    except np.linalg.LinAlgError:
        return transient, None
    if not np.all(np.isfinite(N)) or np.any(N < -1e-9):
        return transient, None
    return transient, N


def _closure(P: TransitionMatrix, seed: set[str]) -> set[str]:
    """`seed` 중 하나에라도 도달할 수 있는 상태 집합(자기 자신 포함)."""
    out = set(seed)
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(P.states):
            if s in out:
                continue
            for j, t in enumerate(P.states):
                if t in out and P.matrix[i, j] > 0:
                    out.add(s)
                    changed = True
                    break
    return out


def expected_steps_to_exit(P: TransitionMatrix) -> pd.DataFrame:
    """각 화면에서 EXIT 까지의 기대 걸음 수.

    **EXIT 에 확률 1로 닿지 못하면 `inf` 다.** 여기가 조용히 틀리기 쉬운 자리다:
    "EXIT 로 가는 길이 있으니 유한"이 **아니다.** 도중에 빠져나올 수 없는 곳으로 갈
    확률이 조금이라도 있으면 기대값은 발산한다. 그 경우까지 역행렬을 밀어붙이면
    "평균 3.7걸음이면 나간다" 같은 그럴듯한 거짓말이 나온다.

    그래서 두 단계로 거른다. ① EXIT 에 도달 **못** 하는 상태(`dead`)를 찾고,
    ② 거기 도달할 수 있는 상태까지 전부 오염(`tainted`)으로 본다. 남은 상태들은
    후속 상태가 전부 깨끗하거나 EXIT 이므로 `I - Q` 가 반드시 가역이다.
    """
    transient = [s for s in P.states if s not in (EXIT, START)]
    if not transient:
        return pd.DataFrame({"state": [], "expected_steps": []})

    reaches_exit = _closure(P, {EXIT}) if EXIT in P.states else set()
    dead = {s for s in P.states if s not in reaches_exit}
    tainted = _closure(P, dead) if dead else set()
    good = [s for s in transient if s not in tainted]

    steps = {s: float(np.inf) for s in transient}
    if good:
        idx = [P.states.index(s) for s in good]
        Q = P.matrix[np.ix_(idx, idx)]
        N = np.linalg.inv(np.eye(len(good)) - Q)
        for state, value in zip(good, N.sum(axis=1)):
            steps[state] = float(value)
    return pd.DataFrame(
        {"state": transient, "expected_steps": [steps[s] for s in transient]}
    )


def absorption_probabilities(
    P: TransitionMatrix, absorbing: tuple[str, ...] = (EXIT,)
) -> pd.DataFrame:
    """전이 상태에서 각 흡수 상태에 결국 닿을 확률. 행 합은 1이다."""
    transient, N = _fundamental(P, absorbing=absorbing)
    if not transient or N is None:
        return pd.DataFrame(
            {"state": transient, **{a: [np.nan] * len(transient) for a in absorbing}}
        )
    t_idx = [P.states.index(s) for s in transient]
    a_idx = [P.states.index(a) for a in absorbing]
    R = P.matrix[np.ix_(t_idx, a_idx)]
    B = N @ R
    out = {"state": transient}
    for k, name in enumerate(absorbing):
        out[name] = B[:, k]
    return pd.DataFrame(out)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_markov_absorption.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/markov.py tests/analytics/metrics/test_markov_absorption.py
git commit -m "feat: add expected steps to exit and absorption probabilities"
```

---

### Task 6: PMI 와 불변식 속성 테스트

**Files:**
- Modify: `analytics/metrics/markov.py`
- Create: `tests/analytics/metrics/test_markov_pmi.py`
- Create: `tests/analytics/metrics/test_markov_invariants.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_markov_pmi.py`:

```python
import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import pointwise_mutual_information, transition_matrix


def _edges(rows):
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


def test_independent_transitions_have_zero_pmi():
    # 2x2 곱 구조: 관측이 독립 예측과 같으면 PMI = 0.
    P = transition_matrix(
        _edges([("A", "X", 1), ("A", "Y", 1), ("B", "X", 1), ("B", "Y", 1)])
    )
    got = pointwise_mutual_information(P)
    assert np.allclose(got["pmi"], 0.0, atol=1e-12)


def test_over_represented_transition_has_positive_pmi():
    P = transition_matrix(
        _edges([("A", "X", 9), ("A", "Y", 1), ("B", "X", 1), ("B", "Y", 9)])
    )
    got = pointwise_mutual_information(P).set_index(["from_state", "to_state"])["pmi"]
    assert got[("A", "X")] > 0
    assert got[("A", "Y")] < 0


def test_pmi_only_reports_observed_transitions():
    P = transition_matrix(_edges([("A", "X", 1), ("B", "Y", 1)]))
    got = pointwise_mutual_information(P)
    assert len(got) == 2


def test_pmi_carries_the_count_so_thin_cells_can_be_filtered():
    P = transition_matrix(_edges([("A", "X", 7)]))
    assert int(pointwise_mutual_information(P).iloc[0]["cnt"]) == 7


def test_pmi_is_symmetric_in_the_information_sense():
    # PMI(a,b) 는 log p(a,b)/(p(a)p(b)) 이므로 카운트 행렬을 전치하면 값이 보존된다.
    rows = [("A", "X", 9), ("A", "Y", 1), ("B", "X", 1), ("B", "Y", 9)]
    forward = pointwise_mutual_information(transition_matrix(_edges(rows)))
    flipped = pointwise_mutual_information(
        transition_matrix(_edges([(t, f, c) for f, t, c in rows]))
    )
    a = forward.set_index(["from_state", "to_state"])["pmi"][("A", "X")]
    b = flipped.set_index(["from_state", "to_state"])["pmi"][("X", "A")]
    assert a == pytest.approx(b)
```

`tests/analytics/metrics/test_markov_invariants.py`:

```python
"""무작위 체인에 대한 속성 기반 불변식 검증.

마르코프 수식 버그는 예외를 안 던지고 그럴듯한 숫자를 낸다. 손계산 대조만으로는
좁으므로 무작위 입력에서 불변식이 깨지는지 본다.
"""
import numpy as np
import pandas as pd
import pytest

from analytics.metrics.markov import (
    EXIT,
    absorption_probabilities,
    expected_steps_to_exit,
    stationary_distribution,
    transition_matrix,
)

SEEDS = list(range(25))


def _random_chain(seed: int) -> pd.DataFrame:
    """모든 화면에서 EXIT 가 도달 가능한 무작위 체인."""
    rng = np.random.default_rng(seed)
    n = int(rng.integers(2, 7))
    screens = [f"S{i}" for i in range(n)]
    rows = []
    for s in screens:
        for t in screens:
            if rng.random() < 0.5:
                rows.append((s, t, int(rng.integers(1, 100))))
        rows.append((s, EXIT, int(rng.integers(1, 100))))  # 항상 이탈 경로가 있다
    return pd.DataFrame(
        [{"from_state": f, "to_state": t, "cnt": c} for f, t, c in rows]
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_rows_always_sum_to_one(seed):
    P = transition_matrix(_random_chain(seed))
    assert np.allclose(P.matrix.sum(axis=1), 1.0)


@pytest.mark.parametrize("seed", SEEDS)
def test_stationary_always_sums_to_one_and_is_non_negative(seed):
    pi = stationary_distribution(transition_matrix(_random_chain(seed)))["pi"]
    assert pi.sum() == pytest.approx(1.0)
    assert (pi >= -1e-9).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_expected_steps_are_finite_and_at_least_one(seed):
    # 모든 화면에 EXIT 경로가 있으므로 유한해야 한다.
    steps = expected_steps_to_exit(transition_matrix(_random_chain(seed)))
    assert np.all(np.isfinite(steps["expected_steps"]))
    assert (steps["expected_steps"] >= 1.0 - 1e-9).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_absorption_probabilities_sum_to_one(seed):
    got = absorption_probabilities(transition_matrix(_random_chain(seed)))
    assert np.allclose(got[EXIT], 1.0)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_markov_pmi.py -q`
Expected: FAIL — `ImportError: cannot import name 'pointwise_mutual_information'`

- [ ] **Step 3: 구현 — `markov.py` 끝에 추가**

```python
def pointwise_mutual_information(P: TransitionMatrix) -> pd.DataFrame:
    """관측 전이가 독립 가정보다 얼마나 흔한가.

    `PMI(i,j) = log( p(i,j) / (p(i)·p(j)) )`. 양수면 그 쌍이 예상보다 자주 일어난다.
    빈도 순위와 달리 "흔한 화면이라 흔한" 전이를 걸러낸다.

    `cnt` 를 함께 낸다 — 얇은 셀의 PMI 는 크게 튀므로 소비자가 걸러야 한다.
    """
    total = P.counts.sum()
    if total <= 0:
        raise ValueError("no transitions")
    p_from = P.counts.sum(axis=1) / total
    p_to = P.counts.sum(axis=0) / total

    rows = []
    for i, f in enumerate(P.states):
        for j, t in enumerate(P.states):
            c = P.counts[i, j]
            if c <= 0:
                continue
            joint = c / total
            expected = p_from[i] * p_to[j]
            rows.append(
                {
                    "from_state": f,
                    "to_state": t,
                    "cnt": c,
                    "pmi": float(np.log(joint / expected)),
                }
            )
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/ -q`
Expected: PASS (PMI 5 + 불변식 100 + 앞선 태스크 전부)

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/markov.py tests/analytics/metrics/test_markov_pmi.py \
        tests/analytics/metrics/test_markov_invariants.py
git commit -m "feat: add PMI and property-based invariant tests for the chain"
```

---

### Task 7: 기술통계 — UV·PV·세션

**Files:**
- Create: `analytics/metrics/descriptive.py`
- Create: `tests/analytics/metrics/test_descriptive.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_descriptive.py`:

```python
import pandas as pd
import pytest

from analytics.metrics.descriptive import SESSION_AXES, engagement, uv_pv
from analytics.metrics.frame import NonAdditiveMeasureError


def _session_cube() -> pd.DataFrame:
    """전체 조합 2행 + os 접은 롤업 + 전체 롤업."""
    return pd.DataFrame([
        {"period": "2026-07-27", "service_type": "app", "os": "android",
         "gender": "M", "age_band": "30", "daypart": "주간", "app_version": "9.5.1",
         "sessions": 10, "uv": 8, "pv": 40, "events": 100, "duration_sum": 600},
        {"period": "2026-07-27", "service_type": "app", "os": "ios",
         "gender": "M", "age_band": "30", "daypart": "주간", "app_version": "9.5.1",
         "sessions": 5, "uv": 4, "pv": 15, "events": 50, "duration_sum": 300},
        {"period": "2026-07-27", "service_type": "app", "os": None,
         "gender": "M", "age_band": "30", "daypart": "주간", "app_version": "9.5.1",
         "sessions": 15, "uv": 11, "pv": 55, "events": 150, "duration_sum": 900},
        {"period": None, "service_type": None, "os": None, "gender": None,
         "age_band": None, "daypart": None, "app_version": None,
         "sessions": 15, "uv": 11, "pv": 55, "events": 150, "duration_sum": 900},
    ])


def test_uv_pv_reads_uv_from_the_rollup_row_not_by_summing():
    # android 8 + ios 4 = 12 이지만 실제 UV 는 11이다. 합산하면 조용히 부푼다.
    got = uv_pv(_session_cube(), folded=("os",))
    assert int(got.iloc[0]["uv"]) == 11
    assert int(got.iloc[0]["pv"]) == 55


def test_uv_pv_on_full_combination_rows_keeps_each_segment():
    got = uv_pv(_session_cube(), folded=())
    assert len(got) == 2
    assert set(got["os"]) == {"android", "ios"}


def test_engagement_divides_by_sessions_and_users():
    got = engagement(_session_cube(), folded=("os",)).iloc[0]
    assert got["sessions_per_user"] == pytest.approx(15 / 11)
    assert got["pv_per_session"] == pytest.approx(55 / 15)
    assert got["seconds_per_session"] == pytest.approx(900 / 15)


def test_engagement_reports_the_session_span_definition_of_dwell():
    # 세션 큐브의 duration 은 세션 span(초)이고 커버리지 100% 다.
    got = engagement(_session_cube(), folded=("os",)).iloc[0]
    assert got["dwell_definition"] == "session_span_seconds"


def test_zero_sessions_yield_nan_not_a_division_error():
    empty = _session_cube().iloc[[0]].copy()
    empty.loc[:, ["sessions", "uv"]] = 0
    got = engagement(empty, folded=()).iloc[0]
    assert pd.isna(got["pv_per_session"])
    assert pd.isna(got["sessions_per_user"])


def test_uv_is_never_summed_even_if_asked_for_a_missing_rollup():
    # 요청한 롤업 조합이 큐브에 없으면 합산으로 때우지 않고 거부한다.
    cube = _session_cube()
    cube = cube[cube["os"].notna()]  # 롤업 행 제거
    with pytest.raises(NonAdditiveMeasureError, match="uv"):
        uv_pv(cube, folded=("os",))


def test_session_axes_match_the_cube():
    assert SESSION_AXES == (
        "period", "service_type", "os", "gender", "age_band", "daypart", "app_version",
    )
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_descriptive.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.metrics.descriptive'`

- [ ] **Step 3: 구현**

`analytics/metrics/descriptive.py`:

```python
"""기술통계. 세션 큐브 프레임만 받는 순수 함수다.

**`uv` 는 절대 합산하지 않는다.** 롤업은 큐브가 `GROUPING SETS` 로 미리 만들어 두었고,
없는 조합을 요청하면 합산으로 때우지 않고 거부한다. 같은 유저가 이틀 방문하면 1이지
2가 아니다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.metrics.frame import NonAdditiveMeasureError, rollup_rows

SESSION_AXES = (
    "period", "service_type", "os", "gender", "age_band", "daypart", "app_version",
)

# 세션 큐브의 체류는 세션 span(첫→마지막 이벤트, 초)이라 커버리지가 100% 다.
# 전이 큐브의 `dur_sum`(UsagePage 기반, 57~69%)과 **다른 정의**이므로 이름을 붙여 낸다.
DWELL_DEFINITION = "session_span_seconds"


def _rows(cube: pd.DataFrame, folded: tuple[str, ...]) -> pd.DataFrame:
    rows = rollup_rows(cube, SESSION_AXES, folded=folded)
    if rows.empty and folded:
        raise NonAdditiveMeasureError(
            f"the cube has no rollup row with {list(folded)} folded, and uv cannot be "
            "summed to make one; rebuild the cube with that grouping set"
        )
    return rows


def uv_pv(cube: pd.DataFrame, folded: tuple[str, ...] = ()) -> pd.DataFrame:
    """UV·PV·세션·이벤트. `folded` 축은 큐브의 롤업 행에서 읽는다."""
    rows = _rows(cube, folded)
    keep = [a for a in SESSION_AXES if a not in folded]
    return rows[keep + ["sessions", "uv", "pv", "events"]].reset_index(drop=True)


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return np.where(denominator > 0, numerator / denominator, np.nan)


def engagement(cube: pd.DataFrame, folded: tuple[str, ...] = ()) -> pd.DataFrame:
    """유저당 세션, 세션당 PV, 세션당 체류(초)."""
    rows = _rows(cube, folded)
    keep = [a for a in SESSION_AXES if a not in folded]
    out = rows[keep].copy().reset_index(drop=True)
    out["sessions_per_user"] = _ratio(rows["sessions"], rows["uv"])
    out["pv_per_session"] = _ratio(rows["pv"], rows["sessions"])
    out["seconds_per_session"] = _ratio(rows["duration_sum"], rows["sessions"])
    out["dwell_definition"] = DWELL_DEFINITION
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_descriptive.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/descriptive.py tests/analytics/metrics/test_descriptive.py
git commit -m "feat: add descriptive metrics that read uv from the cube rollup"
```

---

### Task 8: 전이 큐브의 체류 — 커버리지를 값과 함께

**Files:**
- Modify: `analytics/metrics/descriptive.py`
- Create: `tests/analytics/metrics/test_transition_dwell.py`

전이 큐브의 `dur_sum` 은 `UsagePage` 기반이라 커버리지가 57~69% 다.
`dur_sum / cnt` 는 커버리지만큼 축소된 **틀린 값**이다. 반드시 `dur_sum / dur_n` 이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_transition_dwell.py`:

```python
import pandas as pd
import pytest

from analytics.metrics.descriptive import screen_dwell


def _edges() -> pd.DataFrame:
    return pd.DataFrame([
        {"from_state": "top/A", "to_state": "top/B", "cnt": 100,
         "dur_sum": 600.0, "dur_n": 60},
        {"from_state": "top/A", "to_state": "EXIT", "cnt": 50,
         "dur_sum": 400.0, "dur_n": 40},
        {"from_state": "top/B", "to_state": "EXIT", "cnt": 20,
         "dur_sum": 0.0, "dur_n": 0},
    ])


def test_mean_dwell_divides_by_measured_visits_not_by_transitions():
    # top/A: dur_sum 1000 / dur_n 100 = 10.0 초.
    # cnt 150 으로 나누면 6.67 초 — 커버리지만큼 축소된 틀린 값.
    got = screen_dwell(_edges()).set_index("state")
    assert got.loc["top/A", "seconds_per_visit"] == pytest.approx(10.0)


def test_coverage_is_reported_next_to_the_value():
    got = screen_dwell(_edges()).set_index("state")
    assert got.loc["top/A", "coverage"] == pytest.approx(100 / 150)


def test_a_screen_with_no_measured_dwell_yields_nan_not_zero():
    # 0 으로 내면 "체류가 0초"와 "체류를 모른다"가 구분되지 않는다.
    got = screen_dwell(_edges()).set_index("state")
    assert pd.isna(got.loc["top/B", "seconds_per_visit"])
    assert got.loc["top/B", "coverage"] == pytest.approx(0.0)


def test_visits_are_the_sum_of_outgoing_transitions():
    got = screen_dwell(_edges()).set_index("state")
    assert int(got.loc["top/A", "visits"]) == 150


def test_exit_is_not_a_screen_so_it_has_no_dwell_row():
    assert "EXIT" not in set(screen_dwell(_edges())["state"])


def test_dwell_definition_is_labelled_differently_from_the_session_cube():
    # 세션 큐브의 session_span_seconds 와 섞이면 안 된다.
    got = screen_dwell(_edges())
    assert set(got["dwell_definition"]) == {"usagepage_seconds"}
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_transition_dwell.py -q`
Expected: FAIL — `ImportError: cannot import name 'screen_dwell'`

- [ ] **Step 3: 구현 — `descriptive.py` 끝에 추가**

```python
# 전이 큐브의 체류는 `UsagePage` 행에서 오고 커버리지가 축마다 다르다(실측 57~69%).
# 세션 큐브의 `session_span_seconds` 와 **다른 정의**다. 이름으로 구분한다.
TRANSITION_DWELL_DEFINITION = "usagepage_seconds"


def screen_dwell(edges: pd.DataFrame) -> pd.DataFrame:
    """화면별 방문당 체류(초)와 그 커버리지.

    **분모는 `cnt` 가 아니라 `dur_n` 이다.** `dur_sum / cnt` 는 체류가 측정되지 않은
    방문까지 분모에 넣어 커버리지만큼 축소된 값을 낸다. 옳은 값은 "체류가 측정된
    방문"에 대한 조건부 평균이고, `dur_n / cnt` 가 그 커버리지다.

    측정된 방문이 하나도 없으면 `NaN` 이다 — 0 으로 내면 "0초 머물렀다"와
    "얼마나 머물렀는지 모른다"가 구분되지 않는다.
    """
    grouped = (
        edges.groupby("from_state", as_index=False)[["cnt", "dur_sum", "dur_n"]].sum()
    )
    grouped = grouped[~grouped["from_state"].isin((START, EXIT))]
    out = pd.DataFrame({"state": grouped["from_state"].to_numpy()})
    out["visits"] = grouped["cnt"].to_numpy()
    out["measured_visits"] = grouped["dur_n"].to_numpy()
    out["seconds_per_visit"] = _ratio(grouped["dur_sum"], grouped["dur_n"])
    out["coverage"] = _ratio(grouped["dur_n"], grouped["cnt"])
    out["dwell_definition"] = TRANSITION_DWELL_DEFINITION
    return out.reset_index(drop=True)
```

`analytics/metrics/descriptive.py` 상단 임포트에 상태 이름 규약을 추가한다 —
문자열 리터럴로 다시 적으면 `markov.py` 와 갈라진다:

```python
from analytics.metrics.markov import EXIT, START
```

`markov.py` 는 순수 모듈이므로 Task 2의 순수성 테스트를 깨지 않는다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/ -q`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/descriptive.py tests/analytics/metrics/test_transition_dwell.py
git commit -m "feat: compute screen dwell against measured visits with coverage"
```

---

### Task 9: 결과 봉투 (커버리지·품질경고·사전 버전)

**Files:**
- Create: `analytics/metrics/envelope.py`
- Create: `tests/analytics/metrics/test_envelope.py`

스펙의 "결과에 항상 동봉하는 것"을 구조화한다. 이게 없으면 소비자가 57% 커버리지짜리
체류를 전수로 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/metrics/test_envelope.py`:

```python
import pandas as pd
import pytest

from analytics.metrics.envelope import Envelope, quality_warnings


def _quality() -> pd.DataFrame:
    return pd.DataFrame([
        {"service_code": "top", "app_version": "9.5.1",
         "check_name": "null_action_name", "violated": 198, "total": 1000},
        {"service_code": "top", "app_version": "9.5.1",
         "check_name": "screen_without_dwell", "violated": 430, "total": 1000},
        {"service_code": "top", "app_version": "9.5.1",
         "check_name": "session_no_screen", "violated": 5, "total": 1000},
    ])


def test_warnings_fire_above_the_threshold():
    got = quality_warnings(_quality(), thresholds={"null_action_name": 0.1})
    assert len(got) == 1
    assert got[0]["check_name"] == "null_action_name"
    assert got[0]["ratio"] == pytest.approx(0.198)


def test_warnings_stay_silent_below_the_threshold():
    assert quality_warnings(_quality(), thresholds={"session_no_screen": 0.5}) == []


def test_a_check_with_no_threshold_is_not_a_warning():
    assert quality_warnings(_quality(), thresholds={}) == []


def test_zero_total_does_not_divide_by_zero():
    frame = pd.DataFrame([
        {"service_code": "top", "app_version": "9.5.1",
         "check_name": "null_action_name", "violated": 0, "total": 0},
    ])
    assert quality_warnings(frame, thresholds={"null_action_name": 0.0}) == []


def test_envelope_carries_everything_the_spec_requires():
    env = Envelope(
        state_dict_version="sd_abc",
        services=["top", "media"],
        requested_dates=["2026-07-26", "2026-07-27"],
        present_dates=["2026-07-26", "2026-07-27"],
        coverage={"dwell": 0.57},
        warnings=[],
    )
    d = env.as_dict()
    for key in ("state_dict_version", "services", "requested_dates",
                "present_dates", "missing_dates", "coverage", "warnings"):
        assert key in d


def test_envelope_derives_missing_dates():
    env = Envelope(
        state_dict_version="sd_abc",
        services=["top"],
        requested_dates=["2026-07-26", "2026-07-27"],
        present_dates=["2026-07-26"],
        coverage={},
        warnings=[],
    )
    assert env.as_dict()["missing_dates"] == ["2026-07-27"]
    assert env.as_dict()["is_complete"] is False


def test_envelope_records_the_service_scope_because_the_cube_does_not():
    # 세션의 44.7% 가 여러 서비스에 걸쳐서 service_code 가 세션 큐브의 축이 될 수 없다.
    # 그래서 "이 숫자가 어떤 서비스 범위인가"는 봉투에만 있다.
    env = Envelope(
        state_dict_version="sd_abc", services=["top", "media"],
        requested_dates=[], present_dates=[], coverage={}, warnings=[],
    )
    assert env.as_dict()["services"] == ["top", "media"]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_envelope.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.metrics.envelope'`

- [ ] **Step 3: 구현**

`analytics/metrics/envelope.py`:

```python
"""결과에 항상 동봉하는 맥락.

스펙: 커버리지 / 성연령 매칭률 / 품질 경고 / state 사전 버전 / 비교 안전성.
이게 없으면 소비자가 커버리지 57% 짜리 체류를 전수로 읽는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Envelope:
    """지표 프레임과 함께 다니는 맥락."""

    state_dict_version: str
    # 큐브가 어떤 서비스 범위로 빌드됐는지. 세션의 44.7% 가 여러 서비스에 걸쳐
    # `service_code` 를 세션 큐브 축으로 둘 수 없으므로, 범위는 여기에만 있다.
    services: list[str]
    requested_dates: list[str]
    present_dates: list[str]
    coverage: dict[str, float] = field(default_factory=dict)
    warnings: list[dict] = field(default_factory=list)

    @property
    def missing_dates(self) -> list[str]:
        present = set(self.present_dates)
        return [d for d in self.requested_dates if d not in present]

    def as_dict(self) -> dict:
        return {
            "state_dict_version": self.state_dict_version,
            "services": list(self.services),
            "requested_dates": list(self.requested_dates),
            "present_dates": list(self.present_dates),
            "missing_dates": self.missing_dates,
            "is_complete": not self.missing_dates,
            "coverage": dict(self.coverage),
            "warnings": list(self.warnings),
        }


def quality_warnings(quality_cube, thresholds: dict[str, float]) -> list[dict]:
    """`violated / total` 이 임계치를 넘은 검사만 경고로 낸다.

    막지 않고 경고만 한다 — 스펙의 "막을 것과 경고할 것을 구분한다" 원칙이다.
    계산이 틀리게 되는 것(uv 합산, 부분 빌드)은 막고, 해석에 주의가 필요한
    것(커버리지·로깅 편차)은 정보를 주고 통과시킨다.
    """
    out = []
    for row in quality_cube.itertuples():
        limit = thresholds.get(row.check_name)
        if limit is None or row.total <= 0:
            continue
        ratio = row.violated / row.total
        if ratio > limit:
            out.append(
                {
                    "check_name": row.check_name,
                    "service_code": row.service_code,
                    "app_version": row.app_version,
                    "ratio": float(ratio),
                    "threshold": float(limit),
                }
            )
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_envelope.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/envelope.py tests/analytics/metrics/test_envelope.py
git commit -m "feat: add the result envelope with coverage and quality warnings"
```

---

### Task 10: `skills/descriptive/` 흡수와 스킬 진입점 갱신

**Files:**
- Delete: `skills/descriptive/sql.py`, `skills/descriptive/run.py`, `skills/descriptive/descriptor.py`
- Delete: `tests/test_descriptive_sql.py`, `tests/test_descriptive_run.py`, `tests/test_descriptive_descriptor.py`
- Modify: `.claude/skills/basic-analysis/SKILL.md`
- Modify: `tests/integration/test_descriptive_live.py`

- [ ] **Step 1: 남은 호출자 확인**

```bash
grep -rnE "skills\.descriptive|skills/descriptive" --include='*.py' --include='*.md' . | grep -v "\.venv"
```

프로덕션 호출자가 나오면 **삭제하지 말고 보고한다.** 나오지 않으면 다음 단계.

- [ ] **Step 2: 옛 엔진 삭제**

```bash
git rm -r skills/descriptive
git rm tests/test_descriptive_sql.py tests/test_descriptive_run.py \
       tests/test_descriptive_descriptor.py
```

`tests/integration/test_descriptive_live.py` 는 옛 좌표(`all_tiara_i`)를 쓰므로 함께
삭제한다 — 1단계에서 그 테이블은 폐기됐다.

```bash
git rm tests/integration/test_descriptive_live.py
```

- [ ] **Step 3: `SKILL.md` 를 새 구조로 갱신**

`.claude/skills/basic-analysis/SKILL.md` 의 "엔진 구동" 절을 아래로 바꾼다:

```markdown
## 엔진

지표 계산은 `analytics/metrics/` 가 담당한다. 이 스킬은 얇은 껍데기다.

큐브가 이미 빌드돼 있어야 한다. 없으면 실패하고 **Trino 로 폴백하지 않는다.**

    .venv/bin/python scripts/build_cubes.py <시작> <끝> <서비스,목록>

기술통계:

    from analytics.metrics import load_cube
    from analytics.metrics.descriptive import engagement, uv_pv

마르코프:

    from analytics.metrics.markov import (
        transition_matrix, exit_probabilities, stationary_distribution,
        expected_steps_to_exit, absorption_probabilities,
        pointwise_mutual_information,
    )

**반드시 지킬 것**

- 비율·평균·확률을 내기 전에 `LoadedCube.require_complete()` 를 호출한다.
  부분 빌드에서 계산하면 틀린 분모로 그럴듯한 답이 나온다.
- `uv` 를 직접 합산하지 않는다. 큐브의 롤업 행에서 읽는다.
- 전이 큐브의 체류는 `dur_sum / dur_n` 이다. `dur_sum / cnt` 는 틀렸다.
- 결과에는 `Envelope` 를 붙여 발행한다.
```

- [ ] **Step 4: 스위트 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 실패 0. 삭제한 테스트 수만큼 총계가 줄어든다. 정확한 수를 보고에 적는다.

- [ ] **Step 5: 커밋**

```bash
git add -u skills tests .claude/skills/basic-analysis/SKILL.md
git commit -m "refactor: absorb the descriptive engine into analytics/metrics"
```

---

### Task 11: 실데이터 스모크

**Files:**
- Create: `tests/analytics/metrics/test_metrics_on_real_cubes.py`

백필된 큐브가 있을 때만 돈다. 손계산 테스트가 못 잡는 것 — 실제 state 이름, 실제
커버리지, 실제 롤업 행 구조 — 을 잡는다.

- [ ] **Step 1: 테스트 작성**

```python
"""빌드된 큐브가 있으면 실데이터로 지표를 돌려본다. 없으면 skip.

손으로 만든 체인은 실제 state 이름·커버리지·롤업 행 구조를 재현하지 못한다.
"""
import glob

import numpy as np
import pandas as pd
import pytest

from analytics.metrics.descriptive import screen_dwell
from analytics.metrics.markov import (
    EXIT,
    expected_steps_to_exit,
    stationary_distribution,
    transition_matrix,
)

TRANSITION = sorted(glob.glob("cache/cubes/transition/*/date=*.parquet"))

pytestmark = pytest.mark.skipif(
    not TRANSITION, reason="빌드된 전이 큐브가 없다 — scripts/build_cubes.py 를 먼저 돌려라"
)


@pytest.fixture(scope="module")
def edges() -> pd.DataFrame:
    df = pd.read_parquet(TRANSITION[-1])
    return df.groupby(["from_state", "to_state"], as_index=False)[
        ["cnt", "dur_sum", "dur_n"]
    ].sum()


def test_the_chain_builds_and_rows_sum_to_one(edges):
    P = transition_matrix(edges)
    assert np.allclose(P.matrix.sum(axis=1), 1.0)


def test_start_and_exit_are_present(edges):
    P = transition_matrix(edges)
    assert "START" in P.states
    assert EXIT in P.states


def test_stationary_sums_to_one_on_real_data(edges):
    assert stationary_distribution(transition_matrix(edges))["pi"].sum() == pytest.approx(1.0)


def test_expected_steps_are_positive_and_plausible(edges):
    steps = expected_steps_to_exit(transition_matrix(edges))
    finite = steps[np.isfinite(steps["expected_steps"])]["expected_steps"]
    assert (finite > 0).all()
    # 화면 전이가 한 세션에 수천 번 일어나지는 않는다. 크게 벗어나면 흡수 구조를 의심한다.
    assert finite.max() < 1000


def test_dwell_coverage_is_between_zero_and_one(edges):
    got = screen_dwell(edges)
    cov = got["coverage"].dropna()
    assert (cov >= 0).all() and (cov <= 1.0 + 1e-9).all()


def test_dwell_is_not_uniformly_zero(edges):
    # 1단계에서 dur_sum 이 100% 0 이던 결함의 회귀 그물.
    assert screen_dwell(edges)["measured_visits"].sum() > 0
```

- [ ] **Step 2: 실행**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_metrics_on_real_cubes.py -q`
Expected: 큐브가 있으면 PASS (6 tests), 없으면 6 skipped.

- [ ] **Step 3: 전체 스위트**

Run: `.venv/bin/python -m pytest -q`
Expected: 실패 0.

- [ ] **Step 4: 커밋**

```bash
git add tests/analytics/metrics/test_metrics_on_real_cubes.py
git commit -m "test: smoke the metrics against real built cubes"
```

---

## 스펙 대비 의도적 차이 2건

**① `metrics/quality.py` 를 따로 만들지 않는다.** 스펙의 모듈 배치에는 있지만, 정합성
검사 자체는 1단계에서 `quality` 큐브의 SQL 이 이미 수행한다(검사 7종). 2단계에 남은 일은
"그 결과를 임계치와 대조해 경고로 바꾸는 것"뿐이라 `envelope.quality_warnings` 하나로
충분하다. 별도 모듈을 만들면 검사 로직이 두 곳에 있는 것처럼 보인다.

**② "state 사전 버전 불일치 거부"는 코드로 강제하지 않는다.** 이미 **구조적으로
불가능**하기 때문이다 — `state_dict_version` 이 캐시 키에 들어가 있어서 `load_cube` 한 번은
한 버전의 큐브만 읽는다. 서로 다른 버전을 섞으려면 두 번 읽어 직접 이어붙여야 하는데,
그건 명시적 행위다. 봉투가 버전을 싣고 다니므로 결과를 비교할 때 눈에 띈다.

## 이 단계에서 특히 의심할 자리

1단계에서 결함 7건이 나온 자리들의 2단계 대응물이다.

1. **롤업 행.** 세션 큐브를 필터 없이 합산하면 2~3배로 부푼다. Task 2의
   `test_summing_the_raw_frame_would_double_count` 가 이걸 고정한다. 새 지표를 만들 때
   **`full_combination_rows` 또는 `rollup_rows` 를 통과했는지** 먼저 확인한다.

2. **분모.** `dur_sum / cnt`(틀림) vs `dur_sum / dur_n`(맞음), `uv` 합산(틀림) vs
   롤업 행 읽기(맞음). 새 비율을 추가할 때 **분모가 무엇을 세는지** 말로 설명해 본다.

3. **부분 빌드.** `read_cube` 는 조용히 일부만 읽는다. 비율을 내기 전에
   `require_complete()` 를 부른다.

4. **그럴듯한 숫자.** 마르코프 수식 버그는 예외를 안 던진다. 해석적 정답
   (2~3 상태 손계산)과 불변식(행 합=1, π=πP, absorption 합=1)을 **둘 다** 건다.
   하나만으로는 좁다.

5. **도달 불가 상태.** EXIT 에 닿을 수 없는 상태를 유사역행렬로 얼버무리면
   "평균 3.7걸음" 같은 거짓말이 나온다. `inf` 로 드러낸다.

6. **두 개의 체류.** `session_span_seconds`(커버리지 100%)와
   `usagepage_seconds`(57~69%)는 다른 정의다. 이름표를 값과 함께 낸다.

## 서브에이전트에게 반드시 넘길 제약

- `git reset --hard`·`git checkout <path>`·`git stash`·`git restore` 금지.
  다른 리비전은 `git show <sha>:<path>` 로 읽는다.
- `git add -A` 금지. 추적되지 않은 `.DS_Store` 가 있다.
- `git commit` 이 권한 분류기에 막히면 우회 시도 금지. 스테이징만 하고 보고한다.
- 라이브 크레덴셜이 필요하면 `$()` 로 셸에 끌어내면 막힌다.
  `.venv/bin/python -c '...'` 안에서 `import env` 후 `os.environ` 에 직접 넣는다.
- **리뷰어에게: 설계 노트를 믿지 말고 계산하라.** 마르코프 지표는 손으로 계산할 수
  있는 크기다. 2~3 상태 체인을 종이에 그려 답을 내고 코드와 대조한다.

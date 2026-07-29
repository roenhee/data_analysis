# 행동층 3단계 (action · cond_transition · path) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 화면층 위에 행동층을 얹어 "화면 안에서 무엇을 눌렀는가"(`action`), "어떤 행동이
다음 화면을 결정하는가"(`cond_transition`), "어떤 순서로 돌아다니는가"(`path`)를 큐브로
만들고, `metrics/actions.py`·`metrics/paths.py` 로 읽는다.

**Architecture:** 1·2단계 구조를 그대로 따른다 — 큐브 SQL은 `analytics/cube/sql.py`,
빌드는 `builder.py` 의 `DEFAULT_CUBE_BUILDERS` 에 세 항목 추가, 지표는 `analytics/metrics/`
의 순수 함수. 세션 귀속은 반드시 기존 `_first_event_attribution` 을 공유한다.

**Tech Stack:** Trino SQL (CTE 단일 SELECT), Python 3.14, pandas, numpy, DuckDB(의미 테스트).

> **이 계획서의 완성도는 균일하지 않다.** Task 1~4 는 코드까지 적혀 있고, Task 5~8 은
> 테스트 이름과 덮어야 할 성질까지만 적혀 있다. 의도적이다 — **Task 1 의 측정 결과가
> Task 2·3 의 `screen` 표현식을 바꾸고**, 그러면 그 뒤 태스크의 코드도 따라 바뀐다.
> Task 1 을 끝낸 사람이 Task 5~8 의 본문을 채운 뒤 진행한다. 지금 채워 넣으면 버려질
> 코드를 쓰는 것이고, 더 나쁘게는 측정 결과와 어긋난 코드를 "계획서에 있으니 맞겠지"
> 하고 따라가게 된다.

---

## 1·2단계에서 넘어온 제약

**① 세션 귀속은 공유 헬퍼로만.** `_first_event_attribution(date)` 를 그대로 쓴다.
새 큐브가 자체 귀속을 쓰면 같은 세션이 큐브마다 다른 날짜·축 버킷에 앉는다.

**② 캐시 키는 큐브별 `sql_hash`.** 새 큐브를 추가해도 기존 세 큐브는 재빌드되지 않는다.
반대로 이 세 큐브의 SQL을 고치면 그 큐브만 다시 만들어진다.

**③ 문자열 테스트는 이 프로젝트의 SQL 결함을 못 잡는다.** 1단계에서 결함 4건이 문자열
테스트 100% 통과 상태로 존재했다. 새 큐브마다 `tests/analytics/test_*_semantics.py`
방식(생성 SQL의 `ev` CTE만 합성 프레임으로 갈아끼워 DuckDB 실행)을 반드시 둔다.

**④ 컷·상한은 반드시 드러낸다.** `dur_n`, `/other` 와 같은 부류다. `path` 큐브의
상위 200 컷은 잘린 꼬리를 행으로 남긴다(Task 4).

**⑤ 서비스는 범위지 축이 아니다.** 세션의 44.7%가 여러 서비스에 걸친다.

---

### Task 1: 화면 이름 공간 측정 (Trino) — **이 태스크가 Task 2·3을 결정한다**

스펙은 두 가지를 동시에 말한다.

- 화면 state = `action.type='Pageview'` 의 **`action.name`** (전이 큐브가 쓰는 것)
- 클릭의 화면 귀속은 **`common.page`** 로 한다 (윈도우 함수 불필요)

**두 이름 공간이 같지 않으면** `action` 큐브의 `screen` 과 `transition` 큐브의 `from_state`
를 조인할 수 없다. "홈탭에서 뭘 눌렀고 그다음 어디로 갔나"가 한 문장으로 안 나온다.
1단계 `quality` 큐브의 `page_name_ambiguous` 가 이미 관련 신호를 재고 있지만, 그건
"이름 하나가 여러 page 를 가리키는가"이지 "두 축이 서로 번역 가능한가"가 아니다.

**Files:**
- Create: `docs/superpowers/measurements/2026-XX-XX-screen-namespace.md` (결과 기록)

- [ ] **Step 1: 대응 관계 측정**

크레덴셜은 `.venv/bin/python -c '...'` 안에서 `import env` 후 `os.environ` 에 직접 넣는다
(`$()` 로 셸에 끌어내면 권한 분류기에 막힌다).

```sql
SELECT
  count(*) AS pageviews,
  count(DISTINCT nullif(trim(action.name), '')) AS names,
  count(DISTINCT nullif(trim(common.page), '')) AS pages,
  count_if(nullif(trim(common.page), '') IS NULL) AS page_null,
  count_if(nullif(trim(action.name), '') IS NULL) AS name_null
FROM bigdata_omega_common_iceberg.axz_tiara.all_tiara_n
WHERE date_id = '2026-07-27' AND c_service_code = 'top'
  AND action.type = 'Pageview'
  AND NULLIF(TRIM(user.uuid), '') IS NOT NULL
  AND coalesce(tag.is_invalid, '0') <> '1'
```

그리고 대응의 함수성(한 `page` 가 몇 개의 `action.name` 을 갖는가):

```sql
SELECT names_per_page, count(*) AS pages
FROM (
  SELECT nullif(trim(common.page), '') AS page,
         count(DISTINCT nullif(trim(action.name), '')) AS names_per_page
  FROM bigdata_omega_common_iceberg.axz_tiara.all_tiara_n
  WHERE date_id = '2026-07-27' AND c_service_code = 'top'
    AND action.type = 'Pageview'
    AND nullif(trim(common.page), '') IS NOT NULL
    AND coalesce(tag.is_invalid, '0') <> '1'
  GROUP BY 1)
GROUP BY 1 ORDER BY 1
```

- [ ] **Step 2: 분기 결정**

| 측정 결과 | Task 2·3 의 `screen` |
|---|---|
| `page → name` 이 **거의 1:1** (다중 대응 page 가 5% 미만) | `page` 로 클릭을 귀속하고, `page → state` 매핑 테이블을 state 사전에 추가해 전이 큐브와 조인 가능하게 한다 |
| 대응이 **깨진다** (다중 대응 10%+ 또는 `page` NULL 이 많다) | 스펙의 "윈도우 함수 불필요"를 **포기**하고, `visit_idx` 방식(1단계 체류 귀속과 동일)으로 클릭을 직전 Pageview 화면에 붙인다. 비용은 전이 큐브와 같은 수준으로 오른다 |

**어느 쪽이든 결과를 문서에 남기고 이 계획서의 Task 2·3을 그에 맞게 고친 뒤 진행한다.**
측정 없이 한쪽을 고르지 않는다 — 스펙의 "실측 확인"은 `page × layer1` 에 대한 것이지
`page × action.name` 에 대한 것이 아니다.

- [ ] **Step 3: 커밋**

```bash
git add docs/superpowers/measurements/
git commit -m "docs: measure whether page and action.name are the same screen namespace"
```

---

### Task 2: `action` 큐브 SQL

**Files:**
- Modify: `analytics/cube/sql.py`
- Create: `tests/analytics/test_cube_sql_action.py`
- Create: `tests/analytics/test_action_semantics.py`

스키마: 7축 + `screen` + `action_kind` + `layer1` + `layer2`, 측정값 `cnt`.
`layer1`·`layer2` 는 state 사전이 이미 갖고 있다(`StateDict.layer1`, `.layer2`).
사전 밖 값은 `other` 로 접는다 — 화면의 `/other` 와 같은 규약이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_cube_sql_action.py`:

```python
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import build_action_cube_sql

ARGS = dict(
    events_table="bigdata_omega_common_iceberg.axz_tiara.all_tiara_n",
    demography_table="hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2",
    date="2026-07-27",
    window_dates=["2026-07-26", "2026-07-27", "2026-07-28"],
    services=["top"],
    versions=["9.5.1"],
    screens=["top/홈탭_진입"],
    layer1=["home_main"],
    layer2=["home_main>SLOT"],
)


def test_action_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_action_cube_sql(**ARGS))


def test_attribution_is_identical_to_the_session_cube():
    from analytics.cube.sql import _first_event_attribution
    assert _first_event_attribution(ARGS["date"]) in build_action_cube_sql(**ARGS)


def test_emits_the_action_layer_columns():
    sql = build_action_cube_sql(**ARGS)
    for col in ("screen", "action_kind", "layer1", "layer2", "cnt"):
        assert col in sql


def test_layer_values_outside_the_dictionary_fold_into_other():
    sql = build_action_cube_sql(**ARGS)
    assert "'home_main'" in sql
    assert "'other'" in sql


def test_layer_list_escapes_single_quotes():
    args = {**ARGS, "layer1": ["o'hara"]}
    assert "o''hara" in build_action_cube_sql(**args)


def test_empty_dictionaries_still_produce_runnable_sql():
    args = {**ARGS, "layer1": [], "layer2": [], "screens": []}
    assert_safe_sql(build_action_cube_sql(**args))
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_cube_sql_action.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_action_cube_sql'`

- [ ] **Step 3: 구현**

`analytics/cube/sql.py` 끝에 추가한다. `screen_expr` 은 **Task 1 의 결정**을 따른다.
아래는 `page` 기반(1:1 확인된 경우)이다.

```python
def _fold(expr: str, allowed: list[str], other: str = "'other'") -> str:
    """사전에 없는 값을 `other` 로 접는다. 화면의 `/other` 와 같은 규약이다."""
    if not allowed:
        return other
    return f"CASE WHEN {expr} IN ({_in_list(allowed)}) THEN {expr} ELSE {other} END"


def build_action_cube_sql(
    events_table: str,
    demography_table: str,
    date: str,
    window_dates: list[str],
    services: list[str],
    versions: list[str],
    screens: list[str],
    layer1: list[str],
    layer2: list[str],
) -> str:
    """화면 안의 행동 분포. 7축 × 화면 × (kind, layer1, layer2) 별 건수.

    클릭의 화면 귀속은 Task 1 의 측정 결과를 따른다 — `common.page` 기반이면 윈도우
    함수가 필요 없고, 대응이 깨지면 `visit_idx` 로 직전 Pageview 에 붙여야 한다.
    """
    axes = CORE_AXIS_NAMES
    axis_cols = "k." + ", k.".join(axes)
    screen_raw = "service_code || '/' || coalesce(nullif(trim(page), ''), '(none)')"
    l1_raw = "coalesce(nullif(trim(layer1), ''), '(none)')"
    l2_raw = f"{l1_raw} || '>' || coalesce(nullif(trim(layer2), ''), '(none)')"
    return (
        _event_cte(events_table, demography_table, window_dates, services, versions)
        + ",\nkept AS (\n"
        "  SELECT\n    uuid,\n    suid,\n"
        f"    {_first_event_axes()}\n"
        + _first_event_attribution(date)
        + "),\n"
        "acts AS (\n"
        "  SELECT uuid, suid,\n"
        f"    {_fold(screen_raw, [f'{s}' for s in screens], other='service_code || ' + chr(39) + '/other' + chr(39))} AS screen,\n"
        "    coalesce(nullif(trim(action_kind), ''), '(none)') AS action_kind,\n"
        f"    {_fold(l1_raw, layer1)} AS layer1,\n"
        f"    {_fold(l2_raw, layer2)} AS layer2\n"
        "  FROM ev\n"
        # 행동층은 클릭 신호만 본다. Pageview·Usage 는 화면층·체류가 이미 쓴다.
        "  WHERE action_type NOT IN ('Pageview', 'Usage')\n"
        ")\n"
        "SELECT\n"
        f"  {axis_cols},\n"
        "  a.screen,\n  a.action_kind,\n  a.layer1,\n  a.layer2,\n"
        "  count(*) AS cnt\n"
        "FROM acts a\n"
        "JOIN kept k ON k.uuid = a.uuid AND k.suid = a.suid\n"
        f"GROUP BY {axis_cols}, a.screen, a.action_kind, a.layer1, a.layer2\n"
    )
```

> **주의:** 위 `_fold(screen_raw, ...)` 의 `other` 인자는 문자열 조립이 지저분하다.
> 구현할 때 `_fold` 를 쓰지 말고 `build_transition_cube_sql` 의 `screen_expr` 패턴을
> 그대로 복제해 `service_code || '/other'` 를 내라. 가독성이 정확성보다 뒤가 아니다.

- [ ] **Step 4: 의미 테스트 작성**

`tests/analytics/test_action_semantics.py` — `test_transition_semantics.py` 의 `_run`
패턴을 그대로 쓴다(`ev` CTE만 합성 프레임으로 교체). 최소 다음을 덮는다:

```python
def test_pageview_and_usage_rows_do_not_become_actions():
    """행동층은 클릭만 센다. 화면 진입이 행동으로 세어지면 분포가 오염된다."""


def test_layer_outside_the_dictionary_folds_to_other():
def test_screen_outside_the_dictionary_folds_to_service_other():
def test_axes_come_from_the_first_event():
def test_a_session_starting_on_an_earlier_day_is_excluded():
def test_counts_are_not_affected_by_adding_pageview_rows():
```

- [ ] **Step 5: 통과 확인 + mutation check**

Run: `.venv/bin/python -m pytest tests/analytics/test_cube_sql_action.py tests/analytics/test_action_semantics.py -q`
Expected: PASS

그다음 결함을 되주입해 테스트가 실제로 잡는지 확인한다(1단계·2단계와 같은 절차):
`WHERE action_type NOT IN (...)` 를 제거하면 `test_pageview_and_usage_rows_do_not_become_actions`
가 실패해야 한다.

- [ ] **Step 6: 커밋**

```bash
git add analytics/cube/sql.py tests/analytics/test_cube_sql_action.py \
        tests/analytics/test_action_semantics.py
git commit -m "feat: add the action cube for in-screen click distribution"
```

---

### Task 3: `cond_transition` 큐브 SQL

**Files:**
- Modify: `analytics/cube/sql.py`
- Create: `tests/analytics/test_cube_sql_cond_transition.py`
- Create: `tests/analytics/test_cond_transition_semantics.py`

"어떤 행동이 다음 화면을 결정하는가". 스키마는 **4축**(`period`, `service_type`, `os`,
`app_version`) + `from_state` + `action_kind` + `to_state`, 측정값 `cnt`.

**축을 4개로 줄인 이유**(스펙): 7축이면 하루 최대 171만 행(전이쌍 3,604 × kind 8)이 되어
코어보다 무거워진다. 성별·연령까지 쪼개 볼 필요가 낮다고 판단했다.

**핵심 구현**: 클릭을 화면 **방문**에 묶어야 하므로 1단계 체류 귀속의 `visit_idx` 를
그대로 재사용한다 — Pageview 와 클릭을 한 스트림에 넣고 그 행까지의 Pageview 수로
방문 번호를 매긴다. 새 기법이 아니라 이미 검증된 것을 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
COND_AXES = ("period", "service_type", "os", "app_version")


def test_uses_only_the_four_reduced_axes():
    sql = build_cond_transition_cube_sql(**ARGS)
    for axis in COND_AXES:
        assert axis in sql
    # 7축을 쓰면 하루 171만 행이 된다.
    assert "gender" not in sql.split("GROUP BY")[-1]
    assert "age_band" not in sql.split("GROUP BY")[-1]


def test_attribution_is_identical_to_the_session_cube():
def test_emits_from_state_action_kind_to_state():
def test_reuses_the_visit_index_to_bind_clicks_to_a_screen():
def test_cond_transition_sql_is_pruned_and_safe():
```

- [ ] **Step 2~5**: Task 2와 같은 절차 — 실패 확인 → 구현 → 의미 테스트 → mutation check.

의미 테스트가 반드시 덮어야 할 것:

```python
def test_a_click_is_attributed_to_the_visit_it_happened_in():
    """홈탭 방문 중 누른 클릭은 홈탭→다음화면 전이에 붙는다."""


def test_a_transition_with_no_click_gets_a_none_action_kind():
    """행동 없이 넘어간 전이도 세어야 한다. 빠뜨리면 분모가 줄어든다."""


def test_the_transition_counts_match_the_transition_cube():
    """같은 세션에 대해 cond_transition 의 cnt 합 == transition 의 cnt.

    행동이 여러 개면 전이 하나가 여러 행으로 쪼개지므로 **합이 커진다.**
    그래서 이 테스트는 '같다'가 아니라 **관계를 고정**한다 —
    행동 없는 전이는 1행, 행동 k개인 전이는 k행.
    """
```

> **⚠️ 여기가 이 단계에서 가장 틀리기 쉬운 자리다.** `cond_transition` 의 `cnt` 를
> 전이 수로 착각하면 안 된다. 클릭이 3개면 같은 전이가 3행으로 나온다.
> 비율을 낼 때 분모가 무엇인지 반드시 문서화한다.

- [ ] **Step 6: 커밋**

```bash
git commit -m "feat: add the conditional transition cube keyed on action kind"
```

---

### Task 4: `path` 큐브 SQL — 상위 200 컷과 **잘린 꼬리**

**Files:**
- Modify: `analytics/cube/sql.py`
- Create: `tests/analytics/test_cube_sql_path.py`
- Create: `tests/analytics/test_path_semantics.py`

스키마: 7축 + `n`(3~5) + `path`, 측정값 `cnt`. 세그먼트×n 당 상위 200.

**컷의 표기 — 이 단계의 열린 결정을 여기서 닫는다.**

상위 200만 남기고 나머지를 버리면 소비자가 "이게 전부"라고 읽는다. `dur_n`·`/other` 와
정확히 같은 문제다. 따라서 **세그먼트×n 마다 `(other)` 행을 하나 남긴다**:

| 컬럼 | 값 |
|---|---|
| `path` | `'(other)'` |
| `cnt` | 잘린 경로들의 건수 합 |
| `distinct_dropped` | 잘린 서로 다른 경로의 개수 |

이러면 총합이 보존되고, `cnt('(other)') / 전체` 가 곧 "상위 200이 놓친 비율"이 된다.
`distinct_dropped` 를 따로 두는 이유는 "200개가 꼬리 전부"인지 "20만 개를 잘랐는지"가
해석을 완전히 바꾸기 때문이다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_path_cube_sql_is_pruned_and_safe():
def test_attribution_is_identical_to_the_session_cube():
def test_emits_n_and_path_and_cnt():


def test_keeps_the_top_200_per_segment_and_n():
    sql = build_path_cube_sql(**ARGS)
    assert "row_number() OVER" in sql
    assert "200" in sql


def test_emits_an_other_row_for_the_truncated_tail():
    # 컷을 조용히 하면 소비자가 상위 200을 전수로 읽는다.
    sql = build_path_cube_sql(**ARGS)
    assert "'(other)'" in sql
    assert "distinct_dropped" in sql


def test_covers_n_from_three_to_five():
    sql = build_path_cube_sql(**ARGS)
    assert "sequence(3, 5)" in sql
```

- [ ] **Step 2: 실패 확인 → Step 3: 구현**

n-gram 은 세션의 화면 배열을 만든 뒤 잘라낸다:

```sql
seq AS (
  SELECT s.uuid, s.suid, array_agg(s.state ORDER BY s.ts) AS states
  FROM screens s JOIN kept k ON k.uuid = s.uuid AND k.suid = s.suid
  GROUP BY s.uuid, s.suid
),
grams AS (
  SELECT g.uuid, g.suid, t.n,
         array_join(slice(g.states, u.i, t.n), '>') AS path
  FROM seq g
  CROSS JOIN UNNEST(sequence(3, 5)) AS t(n)
  -- 길이가 n 보다 짧으면 빈 배열이 되어 그 행이 자연히 빠진다.
  -- `sequence(1, 0)` 은 Trino 에서 에러이므로 `if` 로 감싸야 한다.
  CROSS JOIN UNNEST(
    if(cardinality(g.states) >= t.n,
       sequence(1, cardinality(g.states) - t.n + 1),
       CAST(ARRAY[] AS ARRAY(bigint)))
  ) AS u(i)
)
```

그다음 세그먼트×n 별로 순위를 매기고 상위 200 + `(other)` 를 낸다.

**⚠️ 방언 차이 — 의미 테스트를 DuckDB로 옮길 때 반드시 바꿔야 한다.**

| | Trino | DuckDB |
|---|---|---|
| 부분 배열 | `slice(arr, start, **length**)` | `list_slice(arr, begin, **end**)` |
| 정수열 | `sequence(a, b)` | `generate_series(a, b)` |
| 배열→문자열 | `array_join(arr, '>')` | `array_to_string(arr, '>')` |

`slice` 의 세 번째 인자가 **길이**(Trino)냐 **끝 인덱스**(DuckDB)냐가 다르다. 그대로 옮기면
n-gram 길이가 조용히 틀린다. 알고리즘 자체는 DuckDB 로 검증됐다 — 길이 4 세션은 n=3 에서
2개, n=4 에서 1개, n=5 에서 0개를 낸다.

- [ ] **Step 4: 의미 테스트 — 반드시 덮을 것**

```python
def test_a_session_shorter_than_n_produces_no_ngram():
def test_a_session_of_exactly_n_produces_one_ngram():
def test_a_session_of_n_plus_one_produces_two_overlapping_ngrams():


def test_the_other_row_preserves_the_total():
    """상위 200 + (other) 의 cnt 합 == 컷 이전 전체 합.

    이게 깨지면 경로 분포의 분모가 조용히 틀린다.
    """


def test_distinct_dropped_counts_paths_not_events():
```

- [ ] **Step 5: mutation check + 커밋**

`(other)` 행 생성을 제거하면 `test_the_other_row_preserves_the_total` 이 실패해야 한다.

```bash
git commit -m "feat: add the path cube with an explicit truncated-tail row"
```

---

### Task 5: 빌더 배선

**Files:**
- Modify: `analytics/cube/builder.py`
- Modify: `tests/analytics/test_builder.py`

- [ ] **Step 1: 테스트 추가**

```python
def test_builds_six_cubes_per_date(config):
    written = build_cubes(
        config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
        services=["top"], source_version="sv1", query_fn=FakeQuery(),
    )
    assert len(written) == 6
    assert {p.parent.parent.name for p in written} == {
        "session", "transition", "quality", "action", "cond_transition", "path",
    }


def test_adding_the_new_cubes_does_not_rebuild_the_old_ones(config):
    """새 큐브를 붙여도 기존 세 큐브는 캐시 적중이어야 한다.

    지문이 큐브별이므로 성립한다. 안 그러면 14일 백필을 다시 돌려야 한다.
    """
```

- [ ] **Step 2: 구현**

`DEFAULT_CUBE_BUILDERS` 에 세 항목을 추가하고, 각 빌더가 `state_dict.layer1`·`.layer2`
를 넘기게 한다. `FakeQuery` 의 분기도 새 큐브를 구분하도록 확장한다.

- [ ] **Step 3~4: 통과 확인 + 커밋**

```bash
git commit -m "feat: wire the three action-layer cubes into the builder"
```

---

### Task 6: `metrics/actions.py` — 클릭 분포

**Files:**
- Create: `analytics/metrics/actions.py`
- Create: `tests/analytics/metrics/test_actions.py`

`action` 큐브는 평범한 `GROUP BY` 라 롤업 행이 없다 — `full_combination_rows` 를 통과시켜도
전체가 그대로 나온다. `cnt` 는 가산이다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_click_share_within_a_screen_sums_to_one():
    """화면별 행동 분포는 그 화면 안에서 정규화한다."""


def test_share_is_computed_per_screen_not_globally():
    """전역 정규화하면 트래픽 많은 화면이 분포를 지배한다."""


def test_layer2_rollup_matches_layer1(...):
    """layer1 로 합치면 layer2 합계와 같아야 한다 — 접기 규약 검증."""


def test_other_bucket_is_reported_not_dropped():
```

- [ ] **Step 2~5**: 구현 → 통과 → 커밋.

```bash
git commit -m "feat: add per-screen click distribution metrics"
```

---

### Task 7: `metrics/paths.py` — n-gram 경로

**Files:**
- Create: `analytics/metrics/paths.py`
- Create: `tests/analytics/metrics/test_paths.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_top_paths_are_ranked_by_count():


def test_the_other_row_is_excluded_from_ranking_but_reported_as_coverage():
    """`(other)` 는 경로가 아니라 컷의 크기다. 순위에 섞이면 1위가 될 수도 있다."""


def test_coverage_is_the_share_the_top_paths_actually_cover():
    # 1 - cnt('(other)') / 전체
    

def test_paths_of_different_n_are_never_pooled():
    """n=3 과 n=4 는 다른 모집단이다. 합치면 같은 방문이 여러 번 세어진다."""


def test_a_segment_whose_tail_dominates_is_flagged():
    """`(other)` 가 절반을 넘으면 상위 200이 대표성을 잃는다."""
```

- [ ] **Step 2~5**: 구현 → 통과 → 커밋.

```bash
git commit -m "feat: add n-gram path metrics with explicit tail coverage"
```

---

### Task 8: 실데이터 검증

**Files:**
- Modify: `tests/analytics/metrics/test_metrics_on_real_cubes.py`

- [ ] **Step 1: 하루치 빌드**

```bash
.venv/bin/python scripts/build_cubes.py 2026-07-27 2026-07-27 top \
    --state-dict=<기존 사전 버전>
```

기존 세 큐브는 캐시 적중으로 건너뛰고 새 세 큐브만 만들어진다. 소요 시간을 기록한다 —
`path` 는 n-gram 폭발 가능성이 있어 **가장 비쌀 것으로 예상**한다.

- [ ] **Step 2: 스펙 수치와 대조**

| 큐브 | 스펙 추정 | 실측 |
|---|---|---|
| `action` | 수천 | ? |
| `cond_transition` | ~6만 | ? |
| `path` | 제한적 | ? |

크게 벗어나면 축 표현식이나 컷을 점검한다. `path` 의 `(other)` 비율을 반드시 기록한다 —
절반을 넘으면 상위 200 이 대표성을 잃으므로 컷을 재검토한다.

- [ ] **Step 3: 실데이터 테스트 추가**

```python
@needs_action
def test_click_shares_sum_to_one_per_screen(actions):
@needs_path
def test_path_totals_are_preserved_by_the_other_row(paths):
@needs_cond
def test_cond_transition_counts_relate_to_transition_counts(cond, edges):
```

- [ ] **Step 4: 커밋**

```bash
git commit -m "test: verify the action-layer cubes against real data"
```

---

## 이 단계에서 특히 의심할 자리

1. **화면 이름 공간.** Task 1 없이 진행하면 `action` 큐브와 `transition` 큐브를
   조인할 수 없는 상태로 끝난다. 측정 먼저.

2. **`cond_transition` 의 `cnt` 는 전이 수가 아니다.** 클릭이 k개면 같은 전이가 k행이다.
   비율의 분모를 반드시 명시한다.

3. **`path` 의 컷.** 상위 200을 전수로 읽히게 두지 않는다. `(other)` 행이 총합을
   보존하는지 테스트로 고정한다.

4. **n 별 모집단 분리.** n=3 과 n=4 를 합치면 같은 방문이 여러 번 세어진다.

5. **행동층이 화면층을 오염시키지 않기.** `action` 큐브가 Pageview 를 행동으로 세면
   클릭 분포가 화면 진입으로 부푼다. 문자열로는 안 잡히니 의미 테스트로 잡는다.

## 서브에이전트에게 반드시 넘길 제약

- `git reset --hard`·`git checkout <path>`·`git stash`·`git restore` 금지.
- `git add -A` 금지. 추적되지 않은 `.DS_Store` 가 있다.
- 크레덴셜을 `$()` 로 셸 명령줄에 끌어내면 권한 분류기에 막힌다.
  `.venv/bin/python -c '...'` 안에서 `import env` 후 `os.environ` 에 직접 넣는다.
- **설계 노트를 믿지 말고 실행하라.** 이 프로젝트의 SQL 결함은 문자열 테스트를
  100% 통과한 상태로 존재한다(1단계 4건). 새 테스트마다 결함을 되주입하는
  mutation check 로 실제로 잡히는지 확인한다.

# 행동층 3단계 (action · cond_transition · path) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 화면층 위에 행동층을 얹어 "화면 안에서 무엇을 눌렀는가"(`action`), "어떤 행동이
다음 화면을 결정하는가"(`cond_transition`), "어떤 순서로 돌아다니는가"(`path`)를 큐브로
만들고, `metrics/actions.py`·`metrics/paths.py` 로 읽는다.

**Architecture:** 1·2단계 구조를 그대로 따른다 — 큐브 SQL은 `analytics/cube/sql.py`,
빌드는 `builder.py` 의 `DEFAULT_CUBE_BUILDERS` 에 세 항목 추가, 지표는 `analytics/metrics/`
의 순수 함수. 세션 귀속은 반드시 기존 `_first_event_attribution` 을 공유한다.

**Tech Stack:** Trino SQL (CTE 단일 SELECT), Python 3.14, pandas, numpy, DuckDB(의미 테스트).

> **Task 1 완료 (2026-07-30).** 측정 결과가 두 문서에 있고 분기가 닫혔다:
> `measurements/2026-07-30-screen-namespace.md` · `measurements/2026-07-30-click-stream-shape.md`.
> **Task 2 는 그 결과로 전면 재작성됐고**(아래), Task 3 의 클릭 필터도 바뀌었다.
> Task 5~8 은 본문이 채워졌다.
>
> **측정으로 닫힌 결정 둘:**
> 1. **`common.page` 를 화면으로 쓸 수 없다.** `page → action.name` 이 물량 79~99.5%에서
>    깨진다(`top/default` 하나가 top 트래픽 57%인데 이름 10개). 스펙의 "윈도우 함수 불필요"
>    를 포기하고 `visit_idx` 로 간다. 비용은 전이 큐브 수준으로 오른다.
> 2. **클릭은 `click.layer1` 이 있는 행이다.** 원래 필터
>    `action_type NOT IN ('Pageview','Usage')` 는 하루 31.2억 행을 잡는데 사용자
>    상호작용은 **5.5%(1.71억)** 뿐이다 — 광고 텔레메트리 10.5억(34%), 노출 7.1억,
>    A/B 버킷 3.2억, 앱 생애주기. `action.kind` 목록으로 고르면 `다음검색>클릭`
>    1,722만 건(kind 없음)을 놓치거나 광고를 클릭으로 센다.

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

### ~~Task 1: 화면 이름 공간 측정 (Trino)~~ — **완료 2026-07-30**

**결과: 두 이름 공간은 교차한다.** `page → name` 이 물량 79~99.5%(4개 서비스)에서 깨지고,
역방향으로 `search` 는 `action.name` 이 **1개**뿐인데 `common.page` 는 19개다 — 어느 방향도
전역 함수가 아니다. 분기 B 를 택했다: 전이 큐브와 **같은 화면 식** + `visit_idx` 귀속.

부수 측정으로 클릭의 정의도 바뀌었다(`click-stream-shape.md`). 아래 원문은 당시 판단
기록으로 남긴다.

<details>
<summary>당시 계획 (참고)</summary>

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

</details>

**실제 커밋:** `bb283cd`(화면 이름 공간) · `84695fc`(클릭의 정의).

---

### Task 2: `action` 큐브 SQL — **2026-07-30 재작성**

**Files:**
- Modify: `analytics/cube/sql.py`
- Create: `tests/analytics/test_cube_sql_action.py`
- Create: `tests/analytics/test_action_semantics.py`

스키마: 7축 + `screen` + `action_kind` + `layer1` + `layer2`, 측정값 `cnt`.
**롤업 행 없이 평범한 `GROUP BY`** 다 — `cnt` 는 가산이라 소비자가 합칠 수 있다.

**Task 1 이 정한 것 셋:**

1. **`screen` 은 전이 큐브와 같은 식이다** — `service_code || '/' || action_name`(Pageview 행),
   사전 밖은 `service_code || '/other'`. `common.page` 를 쓰면 `action` 과 `transition` 을
   조인할 수 없다(물량 79~99.5%에서 대응이 깨진다).
2. **클릭은 `nullif(trim(layer1), '') IS NOT NULL` 인 행이다.** `action.kind` 목록으로 고르지
   않는다 — 16.7억 행이 kind 없이 들어오고 그 안에서 진짜 상호작용과 광고 텔레메트리가
   갈리는 기준이 정확히 이 컬럼이다(보유율이 `action.name` 별로 0% 아니면 100%).
3. **귀속할 방문이 없는 클릭은 `START` 에 붙인다.** 첫 Pageview 보다 앞선 클릭(`visit_idx = 0`)
   은 화면이 없다. 조용히 버리면 분포의 분모가 줄어드는데, 전이 큐브가 이미 첫 화면 이전을
   `START` 로 표현하므로 새 표기를 발명하지 않고 총합이 보존되며 `START→X` 엣지와 같은
   좌표에서 읽힌다.

`layer1`·`layer2` 는 state 사전이 갖고 있다(`StateDict.layer1` 45개, `.layer2` 183개).
사전 밖 값은 `other` 로 접는다. **서비스 접두어가 없다** — 사전이 서비스 구분 없이 만들어져
있어서다(`state_sql.build_layer1_count_sql`). 화면과 달리 팀 간 이름 충돌이 섞일 수 있는데,
`search` 만 `layer1` 값이 195개라 접힘이 클 것으로 예상된다. **Task 8 에서 잰다.**

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/analytics/test_cube_sql_action.py`:

```python
"""`action` 큐브 SQL 의 문자열 검사. 의미는 `test_action_semantics.py` 가 본다."""
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
    layer2=["home_main>SEARCH"],
)


def test_action_cube_sql_is_pruned_and_safe():
    assert_safe_sql(build_action_cube_sql(**ARGS))


def test_attribution_is_identical_to_the_session_cube():
    """귀속이 갈라지면 같은 세션이 큐브마다 다른 날짜·축 버킷에 앉는다."""
    from analytics.cube.sql import _first_event_attribution
    assert _first_event_attribution(ARGS["date"]) in build_action_cube_sql(**ARGS)


def test_the_screen_expression_is_identical_to_the_transition_cube():
    """두 큐브를 조인해야 하므로 **같은 식**이어야 한다. `common.page` 는 쓰지 않는다."""
    from analytics.cube.sql import build_transition_cube_sql

    action = build_action_cube_sql(**ARGS)
    transition = build_transition_cube_sql(
        **{k: v for k, v in ARGS.items() if k not in ("layer1", "layer2")}
    )
    screen_expr = (
        "service_code || '/' || coalesce(nullif(trim(action_name), ''), '(none)')"
    )
    assert screen_expr in action and screen_expr in transition
    assert "'/other'" in action
    assert "page" not in action.split("clicks AS (")[-1]


def test_clicks_are_selected_by_the_slot_coordinate_not_the_action_kind():
    """실측: `NOT IN ('Pageview','Usage')` 는 31.2억 행인데 상호작용은 5.5% 다."""
    sql = build_action_cube_sql(**ARGS)
    assert "nullif(trim(layer1), '') IS NOT NULL" in sql
    assert "NOT IN ('Pageview', 'Usage')" not in sql


def test_it_reuses_the_visit_index_to_bind_a_click_to_a_screen():
    sql = build_action_cube_sql(**ARGS)
    assert "sum(is_screen) OVER" in sql
    assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql


def test_a_click_before_the_first_screen_is_attributed_to_start():
    """버리면 분모가 줄어든다. 전이 큐브가 쓰는 표기를 그대로 쓴다."""
    assert "coalesce(v.state, 'START')" in build_action_cube_sql(**ARGS)


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
기대: 전부 `ImportError: cannot import name 'build_action_cube_sql'`

- [ ] **Step 3: 구현 — `analytics/cube/sql.py` 끝에 추가**

```python
def _fold(expr: str, allowed: list[str]) -> str:
    """사전에 없는 값을 `'other'` 로 접는다. 화면의 `/other` 와 같은 규약이다.

    화면과 달리 서비스 접두어가 없다 — `layer1`·`layer2` 사전이 서비스 구분 없이
    만들어져 있어서다(`state_sql.py`).
    """
    if not allowed:
        return "'other'"
    return f"CASE WHEN {expr} IN ({_in_list(allowed)}) THEN {expr} ELSE 'other' END"


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

    **화면 식은 `build_transition_cube_sql` 과 같다.** 그래야 두 큐브를 조인해
    "홈탭에서 무엇을 눌렀고 그다음 어디로 갔나" 를 한 문장으로 물을 수 있다.
    `common.page` 로 귀속하면 윈도우 함수가 필요 없어 싸지만 대응이 깨진다 — 실측에서
    `page → action.name` 이 물량 79~99.5%에서 다중 대응이고, `top/default` 하나가 top
    트래픽의 57%인데 그 안에 이름이 10개다(`measurements/2026-07-30-screen-namespace.md`).

    **클릭은 슬롯 좌표(`layer1`)가 있는 행이다.** `action_type NOT IN ('Pageview','Usage')`
    는 하루 31.2억 행을 잡는데 그중 사용자 상호작용은 5.5%(1.71억)뿐이고 34%가 광고
    텔레메트리다(`measurements/2026-07-30-click-stream-shape.md`). 보유율이 `action.name`
    별로 0% 아니면 100%로 깨끗하게 갈리는 것이 이 기준의 근거다.

    클릭은 `visit_idx` 로 **직전 Pageview** 에 붙인다 — 1단계 체류 귀속에서 이미 검증된
    기법이다. 첫 화면보다 앞선 클릭은 `START` 에 붙인다(전이 큐브의 표기 그대로).

    롤업 행을 만들지 않는다 — `cnt` 는 가산이라 소비자가 합칠 수 있고, `GROUPING SETS` 는
    비가산인 `uv` 때문에 세션 큐브에만 필요하다.
    """
    axes = CORE_AXIS_NAMES
    axis_cols = "k." + ", k.".join(axes)
    screen_raw = (
        "service_code || '/' || coalesce(nullif(trim(action_name), ''), '(none)')"
    )
    if screens:
        screen_expr = (
            f"CASE WHEN {screen_raw} IN ({_in_list(screens)})\n"
            f"              THEN {screen_raw}\n"
            "              ELSE service_code || '/other' END"
        )
    else:
        screen_expr = "service_code || '/other'"
    l1_raw = "trim(layer1)"
    l2_raw = f"{l1_raw} || '>' || coalesce(nullif(trim(layer2), ''), '(none)')"
    return (
        _event_cte(events_table, demography_table, window_dates, services, versions)
        + ",\nkept AS (\n"
        "  SELECT\n    uuid,\n    suid,\n"
        f"    {_first_event_axes(date)}\n"
        + _first_event_attribution(date)
        + "),\n"
        # 화면 신호(Pageview)와 클릭 신호(슬롯 좌표가 있는 행)를 한 스트림에 넣는다.
        "stream AS (\n"
        "  SELECT uuid, suid, ts, action_kind, layer1, layer2,\n"
        f"    CASE WHEN action_type = 'Pageview' THEN {screen_expr} END AS state,\n"
        "    CASE WHEN action_type = 'Pageview' THEN 1 ELSE 0 END AS is_screen\n"
        "  FROM ev\n"
        "  WHERE action_type = 'Pageview'\n"
        "     OR nullif(trim(layer1), '') IS NOT NULL\n"
        "),\n"
        # 각 행을 직전 화면 방문에 묶는다. 같은 ts 면 Pageview 가 먼저 와야 그 방문에
        # 붙는다 — 안 그러면 클릭이 앞 방문으로 새어 간다. `ROWS` 프레임이라 ts 가 같은
        # Pageview 둘도 서로 다른 방문 번호를 받는다.
        "marked AS (\n"
        "  SELECT uuid, suid, state, is_screen, action_kind, layer1, layer2,\n"
        "    sum(is_screen) OVER (PARTITION BY uuid, suid ORDER BY ts, is_screen DESC\n"
        "      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS visit_idx\n"
        "  FROM stream\n"
        "),\n"
        "visits AS (\n"
        "  SELECT uuid, suid, visit_idx, state FROM marked WHERE is_screen = 1\n"
        "),\n"
        # `visit_idx = 0` 은 첫 Pageview 보다 앞선 클릭이라 붙일 방문이 없다.
        # LEFT JOIN 이 NULL 을 주고 `START` 로 채운다 — 버리면 분모가 줄어든다.
        "clicks AS (\n"
        "  SELECT m.uuid, m.suid,\n"
        "    coalesce(v.state, 'START') AS screen,\n"
        "    coalesce(nullif(trim(m.action_kind), ''), '(none)') AS action_kind,\n"
        f"    {_fold(l1_raw, layer1)} AS layer1,\n"
        f"    {_fold(l2_raw, layer2)} AS layer2\n"
        "  FROM marked m\n"
        "  LEFT JOIN visits v\n"
        "    ON v.uuid = m.uuid AND v.suid = m.suid AND v.visit_idx = m.visit_idx\n"
        "  WHERE m.is_screen = 0\n"
        ")\n"
        "SELECT\n"
        f"  {axis_cols},\n"
        "  c.screen,\n  c.action_kind,\n  c.layer1,\n  c.layer2,\n"
        "  count(*) AS cnt\n"
        "FROM clicks c\n"
        "JOIN kept k ON k.uuid = c.uuid AND k.suid = c.suid\n"
        f"GROUP BY {axis_cols}, c.screen, c.action_kind, c.layer1, c.layer2\n"
    )
```

> **`_fold` 를 화면에 쓰지 말 것.** 화면의 `other` 는 `service_code || '/other'` 라 리터럴이
> 아니고, `_fold` 에 끼워 넣으면 문자열 조립이 지저분해진다. 위처럼 `screen_expr` 을 따로
> 쓴다(`build_transition_cube_sql` 과 같은 패턴).

- [ ] **Step 4: 의미 테스트 작성**

`tests/analytics/test_action_semantics.py` — `test_transition_semantics.py` 의 `_run`
패턴을 그대로 쓴다(`WITH ev AS (SELECT * FROM ev_df),` + `sql[sql.index("kept AS ("):]`).
행 만드는 헬퍼도 그 파일에서 복제한다 — **임포트하지 말 것**(`tests/` 를 `sys.path` 에
올리면 `tests/analytics/` 가 진짜 `analytics/` 를 가린다).

```python
def test_a_click_is_attributed_to_the_screen_it_happened_on():
    """홈탭 방문 중 누른 클릭은 `top/홈탭_진입` 행이 된다."""


def test_a_click_before_the_first_pageview_lands_on_start():
    """`visit_idx = 0`. 버리면 분모가 줄어든다 — 총합이 보존되는지 함께 본다."""


def test_pageview_rows_do_not_become_clicks():
    """화면 진입이 클릭으로 세어지면 분포가 오염된다."""


def test_a_row_without_a_slot_coordinate_is_not_a_click():
    """광고 텔레메트리(`axzad_request`)·앱 생애주기(`AppLaunch`)가 여기서 빠진다."""


def test_a_usage_row_is_not_a_click():
    """체류 신호는 화면층이 이미 쓴다."""


def test_the_screen_outside_the_dictionary_folds_to_service_other():


def test_the_layer_outside_the_dictionary_folds_to_other():


def test_layer2_carries_its_layer1_prefix():
    """사전 값이 `layer1>layer2` 형태라 접두어가 없으면 사전과 안 맞는다."""


def test_axes_come_from_the_first_event():


def test_a_session_starting_on_an_earlier_day_is_excluded():


def test_a_second_pageview_at_the_same_timestamp_gets_its_own_visit():
    """`ROWS` 프레임이라 동시각 Pageview 둘이 서로 다른 방문 번호를 받는다.
    `RANGE` 로 바꾸면 둘이 한 방문이 되고 클릭 귀속이 어긋난다.
    """


def test_the_click_total_is_preserved_across_screens():
    """화면별 합 == 클릭 행 수. `START` 를 버리면 여기서 깨진다."""
```

- [ ] **Step 5: 통과 확인 + mutation check**

Run: `.venv/bin/python -m pytest tests/analytics/test_cube_sql_action.py tests/analytics/test_action_semantics.py -q`

되주입할 결함 넷:

1. `WHERE action_type = 'Pageview'\n     OR nullif(trim(layer1), '') IS NOT NULL` 에서
   `OR` 절을 `OR action_type NOT IN ('Pageview', 'Usage')` 로 바꾸면
   `test_a_row_without_a_slot_coordinate_is_not_a_click` 가 실패해야 한다.
2. `coalesce(v.state, 'START')` 를 `v.state` 로 바꾸면
   `test_a_click_before_the_first_pageview_lands_on_start` 와
   `test_the_click_total_is_preserved_across_screens` 가 실패해야 한다.
3. `ORDER BY ts, is_screen DESC` 를 `ORDER BY ts` 로 바꾸면
   `test_a_click_is_attributed_to_the_screen_it_happened_on`(동시각 케이스)이 실패해야 한다.
4. `ROWS BETWEEN` 을 `RANGE BETWEEN` 으로 바꾸면
   `test_a_second_pageview_at_the_same_timestamp_gets_its_own_visit` 가 실패해야 한다.

**넷 중 하나라도 안 잡히면 테스트가 약한 것이 아니라 픽스처가 죽어 있을 수 있다** —
A5 에서 그렇게 통과를 거짓으로 만든 픽스처를 밟았다. 값이 예상과 다르면 픽스처를 먼저 본다.

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
방문 번호를 매긴다. 새 기법이 아니라 이미 검증된 것을 쓴다. **Task 2 의 `stream`·`marked`
CTE 를 그대로 복제한다** — 클릭 필터도 같아야 한다(`layer1` 존재).

**Task 1 이 여기에 정한 것 둘:**

1. **클릭 필터는 Task 2 와 같다** — `nullif(trim(layer1), '') IS NOT NULL`. 이게 갈리면
   `action` 큐브의 `cnt` 합과 `cond_transition` 의 `cnt` 합이 서로 안 맞고, 그 불일치를
   "행동이 여러 개인 전이" 로 오해한다.
2. **`from_state` 는 전이 큐브와 같은 식이다** — 세 큐브(`transition`·`action`·
   `cond_transition`)가 같은 화면 어휘를 써야 조인이 성립한다.

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
    from analytics.cube.sql import _first_event_attribution
    assert _first_event_attribution(ARGS["date"]) in build_cond_transition_cube_sql(
        **ARGS
    )


def test_the_click_filter_is_the_same_as_the_action_cube():
    """갈리면 두 큐브의 `cnt` 합이 안 맞고 그걸 "다중 행동" 으로 오해한다."""
    sql = build_cond_transition_cube_sql(**ARGS)
    assert "nullif(trim(layer1), '') IS NOT NULL" in sql
    assert "NOT IN ('Pageview', 'Usage')" not in sql


def test_the_screen_expression_is_the_same_as_the_transition_cube():
    sql = build_cond_transition_cube_sql(**ARGS)
    assert (
        "service_code || '/' || coalesce(nullif(trim(action_name), ''), '(none)')"
        in sql
    )


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

### Task 5: 빌더 배선 — **2026-07-30 본문 채움**

**Files:**
- Modify: `analytics/cube/builder.py`
- Modify: `tests/analytics/test_builder.py`

- [ ] **Step 1: `FakeQuery` 를 새 큐브까지 판별하게 고친다**

`tests/analytics/test_builder.py` 의 `FakeQuery.__call__` 에서 **`from_state` 분기보다
먼저** 새 분기를 넣는다. `cond_transition` 도 `from_state` 를 갖고 있어서 순서가 바뀌면
전이 큐브 결과를 받는다.

```python
        if "distinct_dropped" in sql:                      # path
            return pd.DataFrame(
                {"n": [3, 3], "path": ["a>b>c", "(other)"], "cnt": [7, 3],
                 "distinct_dropped": [0, 12]}
            )
        if "AS cnt" in sql and "c.action_kind" in sql:      # action
            return pd.DataFrame(
                {"screen": ["top/홈탭_진입"], "action_kind": ["ClickContent"],
                 "layer1": ["home_main"], "layer2": ["other"], "cnt": [9]}
            )
        if "AS cnt" in sql and "from_state" in sql and "action_kind" in sql:
            return pd.DataFrame(                            # cond_transition
                {"from_state": ["top/홈탭_진입"], "action_kind": ["ClickContent"],
                 "to_state": ["EXIT"], "cnt": [4]}
            )
        if "AS cnt" in sql and "from_state" in sql:         # transition
            return pd.DataFrame(
                {"from_state": ["START"], "to_state": ["top/홈탭_진입"], "cnt": [5]}
            )
```

그리고 테스트 둘을 추가한다:

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

    `sql_hash` 가 **큐브별**이라 성립한다(`builder.cube_key_parts`). 안 그러면 15일
    백필을 다시 돌려야 하고, 사전 버전이 같아도 좌표가 흔들린다.
    """
    old = {"session", "transition", "quality"}
    first = build_cubes(
        config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
        services=["top"], source_version="sv1", query_fn=FakeQuery(),
        cube_names=tuple(sorted(old)),
    )
    before = {p: p.stat().st_mtime_ns for p in first}

    build_cubes(
        config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
        services=["top"], source_version="sv1", query_fn=FakeQuery(),
    )
    for path, mtime in before.items():
        assert path.stat().st_mtime_ns == mtime, f"{path} 가 다시 만들어졌다"
```

> **`build_cubes` 에 `cube_names` 인자가 없으면** 위 테스트의 첫 호출을 세 큐브로 좁힐 수
> 없다. 없으면 추가한다(`DEFAULT_CUBE_BUILDERS` 의 부분집합을 받는 형태) — `load_cube_set`
> 이 이미 같은 이름의 인자를 갖고 있으니 규약을 맞춘다.

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/test_builder.py -q`
기대: `test_builds_six_cubes_per_date` 가 `3 != 6` 으로 실패.

- [ ] **Step 3: 구현 — `analytics/cube/builder.py`**

`_transition_builder` 옆에 세 개를 추가하고 레지스트리에 등록한다. **`_window_dates` 를
공유한다** — 창이 갈리면 자정 넘긴 세션이 큐브마다 다르게 잘린다.

```python
def _action_builder(*, state_dict, date, services, events_table, demography_table, **_):
    return build_action_cube_sql(
        events_table=events_table, demography_table=demography_table,
        date=date, window_dates=_window_dates(date), services=services,
        versions=state_dict.app_versions, screens=state_dict.screens,
        layer1=state_dict.layer1, layer2=state_dict.layer2,
    )


def _cond_transition_builder(
    *, state_dict, date, services, events_table, demography_table, **_
):
    return build_cond_transition_cube_sql(
        events_table=events_table, demography_table=demography_table,
        date=date, window_dates=_window_dates(date), services=services,
        versions=state_dict.app_versions, screens=state_dict.screens,
    )


def _path_builder(*, state_dict, date, services, events_table, demography_table, **_):
    return build_path_cube_sql(
        events_table=events_table, demography_table=demography_table,
        date=date, window_dates=_window_dates(date), services=services,
        versions=state_dict.app_versions, screens=state_dict.screens,
    )


DEFAULT_CUBE_BUILDERS = {
    "session": _session_builder,
    "transition": _transition_builder,
    "quality": _quality_builder,
    "action": _action_builder,
    "cond_transition": _cond_transition_builder,
    "path": _path_builder,
}
```

임포트도 추가한다(`from analytics.cube.sql import ...`).

- [ ] **Step 4: 통과 확인 + 커밋**

Run: `.venv/bin/python -m pytest tests -q`

```bash
git add analytics/cube/builder.py tests/analytics/test_builder.py
git commit -m "feat: wire the three action-layer cubes into the builder"
```

---

### Task 6: `metrics/actions.py` — 클릭 분포 — **2026-07-30 본문 채움**

**Files:**
- Create: `analytics/metrics/actions.py`
- Create: `tests/analytics/metrics/test_actions.py`

`action` 큐브는 평범한 `GROUP BY` 라 롤업 행이 없다 — `full_combination_rows` 를 통과시켜도
전체가 그대로 나온다. `cnt` 는 가산이다.

**이 태스크의 핵심은 `clicks_per_visit` 이다.** Task 1 이 화면 식을 전이 큐브와 맞춘 값을
여기서 회수한다 — `action` 의 `screen` 과 `transition` 의 `from_state` 가 같은 값이라
"이 화면에서 방문당 몇 번 누르나" 를 물을 수 있다. 이름 공간이 갈렸으면 불가능한 지표다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
"""화면 안의 클릭 분포. **화면 안에서 정규화하는 것**이 요점이다."""
import pandas as pd
import pytest

from analytics.metrics.actions import click_share, clicks_per_visit


def _actions() -> pd.DataFrame:
    return pd.DataFrame([
        {"screen": "top/홈탭_진입", "action_kind": "ClickContent",
         "layer1": "home_main", "layer2": "home_main>FEED", "cnt": 60},
        {"screen": "top/홈탭_진입", "action_kind": "(none)",
         "layer1": "home_main", "layer2": "home_main>SEARCH", "cnt": 40},
        # 트래픽이 적은 화면 — 전역 정규화하면 이 화면의 분포가 지워진다.
        {"screen": "media/뉴스", "action_kind": "ClickContent",
         "layer1": "m_news", "layer2": "other", "cnt": 2},
        {"screen": "media/뉴스", "action_kind": "Share",
         "layer1": "other", "layer2": "other", "cnt": 8},
    ])


def test_the_share_sums_to_one_within_each_screen():
    got = click_share(_actions(), by=("action_kind",))
    for _, group in got.groupby("screen"):
        assert group["share"].sum() == pytest.approx(1.0)


def test_the_share_is_per_screen_not_global():
    """전역 정규화하면 트래픽 많은 화면이 분포를 지배한다 — media 는 10/110 이 된다."""
    got = click_share(_actions(), by=("action_kind",)).set_index(
        ["screen", "action_kind"]
    )
    assert got.loc[("media/뉴스", "Share"), "share"] == pytest.approx(0.8)
    assert got.loc[("top/홈탭_진입", "ClickContent"), "share"] == pytest.approx(0.6)


def test_the_numerator_ships_with_the_ratio():
    """비율만 내면 소비자가 검산할 수 없다 — 이 층의 규칙이다."""
    got = click_share(_actions(), by=("action_kind",))
    assert {"cnt", "share"} <= set(got.columns)


def test_folding_layer2_into_layer1_preserves_the_total():
    """접기 규약 검증 — layer1 로 합친 값이 layer2 합계와 같아야 한다."""
    one = click_share(_actions(), by=("layer1",)).set_index(["screen", "layer1"])
    two = click_share(_actions(), by=("layer1", "layer2"))
    rolled = two.groupby(["screen", "layer1"])["cnt"].sum()
    for key, value in rolled.items():
        assert one.loc[key, "cnt"] == pytest.approx(value)


def test_the_other_bucket_is_reported_not_dropped():
    """`other` 를 빼면 비중의 분모가 줄어 남은 값이 부푼다."""
    got = click_share(_actions(), by=("layer1",))
    assert "other" in set(got["layer1"])
    assert got[got["screen"] == "media/뉴스"]["share"].sum() == pytest.approx(1.0)


def test_an_empty_frame_gives_an_empty_result_rather_than_raising():
    empty = pd.DataFrame(columns=["screen", "action_kind", "layer1", "layer2", "cnt"])
    assert click_share(empty, by=("action_kind",)).empty


def _edges() -> pd.DataFrame:
    """전이 큐브. `from_state` 가 `action` 큐브의 `screen` 과 **같은 값**이다."""
    return pd.DataFrame([
        {"from_state": "top/홈탭_진입", "to_state": "EXIT", "cnt": 50,
         "dur_sum": 500.0, "dur_n": 50},
        {"from_state": "media/뉴스", "to_state": "EXIT", "cnt": 5,
         "dur_sum": 50.0, "dur_n": 5},
    ])


def test_clicks_per_visit_joins_the_two_cubes_on_the_shared_screen_name():
    """Task 1 이 화면 식을 맞춘 값을 여기서 회수한다."""
    got = clicks_per_visit(_actions(), _edges()).set_index("screen")
    assert got.loc["top/홈탭_진입", "clicks_per_visit"] == pytest.approx(100 / 50)
    assert got.loc["media/뉴스", "clicks_per_visit"] == pytest.approx(10 / 5)


def test_a_screen_with_no_visits_is_nan_not_infinity():
    """방문이 0 이면 "모른다" 다. `inf` 는 그럴듯한 거짓말이다."""
    got = clicks_per_visit(_actions(), _edges().iloc[:1]).set_index("screen")
    assert pd.isna(got.loc["media/뉴스", "clicks_per_visit"])


def test_start_clicks_have_no_visit_and_are_reported_separately():
    """`START` 는 화면이 아니라 방문 수가 없다. 분모를 발명하지 않는다."""
    actions = pd.concat([_actions(), pd.DataFrame([
        {"screen": "START", "action_kind": "AppLaunch", "layer1": "other",
         "layer2": "other", "cnt": 7},
    ])], ignore_index=True)
    got = clicks_per_visit(actions, _edges()).set_index("screen")
    assert got.loc["START", "cnt"] == 7
    assert pd.isna(got.loc["START", "clicks_per_visit"])
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/analytics/metrics/test_actions.py -q`
기대: `ModuleNotFoundError: No module named 'analytics.metrics.actions'`

- [ ] **Step 3: 구현 — `analytics/metrics/actions.py`**

```python
"""화면 안의 행동 분포. `action` 큐브를 읽는 순수 함수.

`action` 큐브는 롤업 행이 없는 평범한 `GROUP BY` 라 `cnt` 를 그냥 합해도 된다 —
세션 큐브의 `GROUPING SETS` 와 다르다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def click_share(
    actions: pd.DataFrame, by: tuple[str, ...] = ("action_kind",)
) -> pd.DataFrame:
    """화면별 `by` 조합의 클릭 건수와 **그 화면 안에서의** 비중.

    **전역으로 정규화하지 않는다.** 트래픽이 많은 화면이 분포를 지배해서, 작은 화면의
    행동 구성이 지워진다 — 실측에서 top 이 클릭의 대부분을 차지한다. 화면 안에서 정규화하면
    "이 화면에 들어온 사람은 무엇을 누르나" 가 되어 화면끼리 견줄 수 있다.

    `other` 버킷(사전 밖 값)을 빼지 않는다. 빼면 분모가 줄어 남은 값이 부푼다.
    비율과 함께 `cnt` 를 낸다 — 소비자가 검산할 수 있어야 한다.
    """
    keys = ["screen", *by]
    if actions.empty:
        return pd.DataFrame(columns=[*keys, "cnt", "share"])
    grouped = actions.groupby(keys, as_index=False, observed=True)["cnt"].sum()
    per_screen = grouped.groupby("screen")["cnt"].transform("sum")
    grouped["share"] = grouped["cnt"] / per_screen
    return grouped.sort_values(["screen", "cnt"], ascending=[True, False],
                               ignore_index=True)


def clicks_per_visit(actions: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    """화면별 방문당 클릭 수. **두 큐브를 화면 이름으로 조인한다.**

    `action` 큐브의 `screen` 과 `transition` 큐브의 `from_state` 가 같은 식으로 만들어져
    있어서 가능하다(`measurements/2026-07-30-screen-namespace.md` 의 결정). `common.page`
    로 귀속했다면 이 지표는 존재할 수 없다.

    방문 수는 그 화면에서 **출발한** 전이 수다. 방문이 없으면 `NaN` 이다 — `inf` 로 내면
    그럴듯한 거짓말이고, 0 으로 내면 "안 누른다" 와 "방문을 모른다" 가 섞인다.
    `START` 는 화면이 아니라 방문 수가 없으므로 항상 `NaN` 이다(분모를 발명하지 않는다).
    """
    clicks = actions.groupby("screen", as_index=False, observed=True)["cnt"].sum()
    visits = (
        edges.groupby("from_state", observed=True)["cnt"].sum()
        .rename("visits").rename_axis("screen").reset_index()
    )
    out = clicks.merge(visits, on="screen", how="left")
    out["clicks_per_visit"] = np.where(
        out["visits"].to_numpy(dtype=float) > 0,
        out["cnt"].to_numpy(dtype=float) / out["visits"].to_numpy(dtype=float),
        np.nan,
    )
    return out.sort_values("cnt", ascending=False, ignore_index=True)
```

- [ ] **Step 4: 통과 확인 + mutation check**

되주입할 결함 둘:

1. `per_screen` 을 `grouped["cnt"].sum()`(전역 합)으로 바꾸면
   `test_the_share_is_per_screen_not_global` 이 실패해야 한다.
2. `np.where(... > 0, ..., np.nan)` 을 나눗셈만 남기면
   `test_a_screen_with_no_visits_is_nan_not_infinity` 가 실패해야 한다.

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/actions.py tests/analytics/metrics/test_actions.py
git commit -m "feat: add per-screen click distribution metrics"
```

---

### Task 7: `metrics/paths.py` — n-gram 경로 — **2026-07-30 본문 채움**

**Files:**
- Create: `analytics/metrics/paths.py`
- Create: `tests/analytics/metrics/test_paths.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
"""n-gram 경로. `(other)` 가 경로가 아니라 **컷의 크기**인 것이 요점이다."""
import pandas as pd
import pytest

from analytics.metrics.paths import OTHER_PATH, path_coverage, top_paths


def _paths() -> pd.DataFrame:
    return pd.DataFrame([
        {"n": 3, "path": "a>b>c", "cnt": 50, "distinct_dropped": 0},
        {"n": 3, "path": "a>b>d", "cnt": 30, "distinct_dropped": 0},
        {"n": 3, "path": OTHER_PATH, "cnt": 20, "distinct_dropped": 400},
        {"n": 4, "path": "a>b>c>d", "cnt": 10, "distinct_dropped": 0},
        {"n": 4, "path": OTHER_PATH, "cnt": 90, "distinct_dropped": 9000},
    ])


def test_top_paths_are_ranked_by_count():
    got = top_paths(_paths(), n=3)
    assert got["path"].tolist() == ["a>b>c", "a>b>d"]
    assert got["cnt"].is_monotonic_decreasing


def test_the_other_row_is_excluded_from_the_ranking():
    """`(other)` 는 경로가 아니라 컷의 크기다. 순위에 섞이면 1위가 될 수도 있다 —
    실측 n=4 에서 그렇다(90 대 10).
    """
    assert OTHER_PATH not in set(top_paths(_paths(), n=4)["path"])


def test_the_share_is_out_of_the_uncut_total():
    """분모는 컷 이전 전체(`(other)` 포함)다. 상위 200 안에서만 정규화하면 부푼다."""
    got = top_paths(_paths(), n=3).set_index("path")
    assert got.loc["a>b>c", "share"] == pytest.approx(0.5)


def test_coverage_is_the_share_the_top_paths_actually_cover():
    assert path_coverage(_paths(), n=3) == pytest.approx(0.8)
    assert path_coverage(_paths(), n=4) == pytest.approx(0.1)


def test_paths_of_different_n_are_never_pooled():
    """n=3 과 n=4 는 다른 모집단이다. 합치면 같은 방문이 여러 번 세어진다."""
    with pytest.raises(ValueError, match="one n at a time"):
        top_paths(_paths(), n=None)


def test_a_segment_whose_tail_dominates_is_flagged():
    """`(other)` 가 절반을 넘으면 상위 200 이 대표성을 잃는다."""
    got = top_paths(_paths(), n=4)
    assert got.attrs["tail_dominates"] is True
    assert top_paths(_paths(), n=3).attrs["tail_dominates"] is False


def test_the_dropped_path_count_is_reported_next_to_the_coverage():
    """커버리지 0.1 이 "200개가 꼬리 전부" 인지 "9,000개를 잘랐" 는지로 해석이 갈린다."""
    got = top_paths(_paths(), n=4)
    assert got.attrs["distinct_dropped"] == 9000


def test_a_missing_n_raises_rather_than_returning_empty():
    with pytest.raises(KeyError, match="no rows for n"):
        top_paths(_paths(), n=5)
```

- [ ] **Step 2: 실패 확인 → Step 3: 구현**

```python
"""n-gram 경로 지표. `path` 큐브를 읽는 순수 함수.

**`(other)` 행은 경로가 아니라 컷의 크기다.** 세그먼트×n 마다 상위 200 만 남기고 나머지를
그 한 행에 접었으므로, 순위에 섞으면 1위가 될 수도 있다(실측 n=4 에서 그렇다).
"""
from __future__ import annotations

import pandas as pd

# `path` 큐브가 잘린 꼬리를 담는 행. `analytics/cube/sql.py` 가 만든다.
OTHER_PATH = "(other)"
# `(other)` 가 이 비중을 넘으면 상위 200 이 대표성을 잃는다.
TAIL_DOMINATES_ABOVE = 0.5


def _one_n(paths: pd.DataFrame, n: int | None) -> pd.DataFrame:
    if n is None:
        raise ValueError(
            "read one n at a time: n=3 and n=4 are different populations and pooling "
            "them counts the same visit more than once"
        )
    rows = paths[paths["n"] == n]
    if rows.empty:
        raise KeyError(f"no rows for n={n}; present: {sorted(set(paths['n']))}")
    return rows


def path_coverage(paths: pd.DataFrame, n: int) -> float:
    """상위 경로가 실제로 덮는 비중 = `1 - (other) / 전체`."""
    rows = _one_n(paths, n)
    total = float(rows["cnt"].sum())
    if total <= 0:
        return float("nan")
    tail = float(rows.loc[rows["path"] == OTHER_PATH, "cnt"].sum())
    return 1.0 - tail / total


def top_paths(paths: pd.DataFrame, n: int) -> pd.DataFrame:
    """`n` 걸음 경로 순위. `(other)` 를 뺀 목록이고 비중은 **컷 이전 전체** 기준이다.

    `attrs` 에 컷의 크기를 함께 싣는다 — 커버리지 0.1 이 "200개가 꼬리 전부" 인지
    "9,000개를 잘랐" 는지로 해석이 완전히 갈린다.
    """
    rows = _one_n(paths, n)
    total = float(rows["cnt"].sum())
    out = rows[rows["path"] != OTHER_PATH].copy()
    out["share"] = out["cnt"] / total if total > 0 else float("nan")
    out = out.sort_values("cnt", ascending=False, ignore_index=True)
    coverage = path_coverage(paths, n)
    out.attrs["coverage"] = coverage
    out.attrs["tail_dominates"] = bool(1.0 - coverage > TAIL_DOMINATES_ABOVE)
    out.attrs["distinct_dropped"] = int(
        rows.loc[rows["path"] == OTHER_PATH, "distinct_dropped"].sum()
    )
    return out
```

> **`attrs` 는 pandas 연산에서 쉽게 사라진다.** `copy()` 는 보존하지만 `merge`·`concat` 은
> 아니다. 분석층으로 올릴 때는 `attrs` 가 아니라 `AnalysisResult.headline` 에 담는다.

- [ ] **Step 4: 통과 확인 + mutation check**

`out["share"] = out["cnt"] / total` 의 `total` 을 `out["cnt"].sum()`(컷 이후 합)으로
바꾸면 `test_the_share_is_out_of_the_uncut_total` 이 실패해야 한다.
`TAIL_DOMINATES_ABOVE` 를 0.95 로 올리면 `test_a_segment_whose_tail_dominates_is_flagged`
가 실패해야 한다.

- [ ] **Step 5: 커밋**

```bash
git add analytics/metrics/paths.py tests/analytics/metrics/test_paths.py
git commit -m "feat: add n-gram path metrics with explicit tail coverage"
```

---

### Task 8: 실데이터 검증 — **2026-07-30 본문 채움**

**Files:**
- Modify: `tests/analytics/metrics/test_metrics_on_real_cubes.py`
- Create: `docs/superpowers/measurements/2026-XX-XX-action-layer-scale.md`

- [ ] **Step 1: 하루치 빌드**

```bash
.venv/bin/python -c 'import runpy; runpy.run_path("<크레덴셜 래퍼>", run_name="__main__")'
```

래퍼 안에서 `sys.path.insert` 후 `import env` 로 `TIARA_ID`·`TIARA_PW` 를 넣고
`scripts/build_cubes.py` 를 `runpy` 로 돌린다 — 크레덴셜을 셸 명령줄에 끌어내면 권한
분류기가 막는다.

```
2026-07-27 2026-07-27 top,media,entertain,sports,content_v,search
    --state-dict=sd_2ab5ec25e750dda2
```

기존 세 큐브는 **캐시 적중으로 건너뛴다**(`sql_hash` 가 큐브별). 새 세 큐브의 소요 시간을
각각 기록한다 — `path` 가 n-gram 폭발 가능성으로 가장 비쌀 것으로 예상한다.

- [ ] **Step 2: 스펙 수치와 대조하고 문서에 남긴다**

| 큐브 | 스펙 추정 | 실측 |
|---|---|---|
| `action` | 수천 | ? |
| `cond_transition` | ~6만 | ? |
| `path` | 제한적 | ? |

**`action` 의 "수천" 추정은 근거가 사라졌다** — 클릭 1.71억 건이 7축 × 화면 × kind ×
layer1 × layer2 로 갈라지고 `layer2` 값만 top 에서 644개다. 크게 벗어나면 `layer2` 를
접거나 축을 줄인다. **지금 미리 접지 않는다** — 근거 없이 해상도를 버리는 것이다.

반드시 함께 기록할 것:

- `path` 의 `(other)` 비중 (n=3,4,5 각각). **절반을 넘으면 상위 200 컷을 재검토한다.**
- `layer1`·`layer2` 의 `other` 비중 — 사전이 45개·183개인데 원천은 `search` 만 `layer1`
  195개다. 화면의 `/other` 처럼 서비스마다 크게 다를 것으로 예상한다(A6 참고).
- **클릭 집합에서 `START` 에 붙은 비중.** 순진한 스트림(31.2억)에서는 2.95%였지만 그 값은
  광고·생애주기가 섞인 것이다 — `AppLaunch` 는 65.4%가 첫 화면 앞이고 `layer1` 이 없어서
  이제 제외된다. **클릭 집합만의 값은 여기서 처음 나온다.**

- [ ] **Step 3: 실데이터 테스트 추가**

`test_metrics_on_real_cubes.py` 의 `needs_cubes` 패턴을 따라 새 큐브용 skip 마커를 만든다
(`_cube_paths("action", {...})`).

```python
@needs_action
def test_click_shares_sum_to_one_per_screen(real_actions):
    from analytics.metrics.actions import click_share

    got = click_share(real_actions, by=("action_kind",))
    for screen, group in got.groupby("screen"):
        assert group["share"].sum() == pytest.approx(1.0), screen


@needs_action
def test_the_click_namespace_matches_the_transition_cube(real_actions, real_cubes):
    """Task 1 의 결정이 실제로 조인 가능한지 — 이게 깨지면 행동층 전체가 무의미하다."""
    screens = set(real_actions["screen"]) - {"START"}
    assert screens <= set(real_cubes.transition["from_state"])


@needs_action
def test_clicks_per_visit_is_finite_for_the_busiest_screens(real_actions, real_cubes):
    from analytics.metrics.actions import clicks_per_visit

    got = clicks_per_visit(real_actions, real_cubes.transition)
    busiest = got[got["cnt"] > 1_000_000]
    assert not busiest["clicks_per_visit"].isna().any()


@needs_path
def test_path_totals_are_preserved_by_the_other_row(real_paths):
    """상위 200 + `(other)` 의 합 == 컷 이전 전체. 깨지면 경로 분포의 분모가 틀린다."""
    from analytics.metrics.paths import path_coverage, top_paths

    for n in (3, 4, 5):
        kept = top_paths(real_paths, n=n)
        assert kept.attrs["coverage"] == pytest.approx(path_coverage(real_paths, n))
        assert 0.0 <= kept.attrs["coverage"] <= 1.0


@needs_cond
def test_cond_transition_counts_relate_to_the_transition_cube(real_cond, real_cubes):
    """`cnt` 는 전이 수가 **아니다** — 클릭이 k개면 같은 전이가 k행이다.

    그래서 `>=` 가 아니라 **관계를 고정**한다: 행동 없는 전이는 1행이므로 합은 전이 수보다
    작을 수 없다.
    """
    edges = real_cubes.transition
    total_transitions = float(edges["cnt"].sum())
    assert float(real_cond["cnt"].sum()) >= total_transitions * 0.9
```

- [ ] **Step 4: 커밋**

```bash
git add tests/analytics/metrics/test_metrics_on_real_cubes.py \
        docs/superpowers/measurements/
git commit -m "test: verify the action-layer cubes against real data"
```

---

## 이 단계에서 특히 의심할 자리

1. ~~**화면 이름 공간.**~~ **측정 완료** — 세 큐브가 **같은 화면 식**을 쓴다.
   `common.page` 를 쓰고 싶어지면 `measurements/2026-07-30-screen-namespace.md` 를 먼저
   읽는다: 물량 79~99.5%에서 대응이 깨지고 `top/default` 하나가 top 트래픽의 57%다.

1b. **"클릭" 의 정의를 느슨하게 하지 말 것.** `action_type NOT IN ('Pageview','Usage')` 는
   하루 31.2억 행이고 그중 **34%가 광고 텔레메트리**다. 세 큐브 모두 필터가
   `nullif(trim(layer1), '') IS NOT NULL` 로 같아야 하고, 갈리면 `cnt` 합이 안 맞는데
   그걸 "다중 행동" 으로 오해하게 된다.

1c. **`layer1`·`layer2` 사전은 서비스 구분이 없다.** 화면과 달리 접두어가 없어서 팀 간
   이름이 섞일 수 있고, `search` 만 `layer1` 값이 195개인데 사전은 45개다. Task 8 에서
   서비스별 `other` 비중을 반드시 재고, 화면의 `/other`(A6: sports 37%)처럼 비대칭이면
   그때 판단한다.

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

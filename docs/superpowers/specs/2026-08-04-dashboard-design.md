# 대시보드 설계 (4단계)

**한 줄**: `analytics/analyses/` 를 직접 부르는 **Streamlit 탐색기**. 상태는 URL 에 있고,
공유는 URL 이다. 발행·저장은 없다.

## 왜 이 형태인가 — 2026-08-04 브레인스토밍에서 좁힘

`specs/2026-07-29-skill-platform-shape-design.md` 의 대시보드 골격("분석을 직접 호출, 자체
계산 없음, 1인~소수 동료, 기술 미정") 위에서 다음을 정했다.

| 결정 | 근거 |
|---|---|
| **Streamlit** | `analyses/` 가 Python 이고 밀리초에 돈다. 위젯으로 세그먼트·파라미터를 받아 표·차트를 그리는 데 가장 가볍다. 프로젝트에 프론트엔드가 없어 첫 UI 다. |
| **공유 = URL(라이브), 발행 없음** | 밀리초 재계산 + 배치 큐브라, 결과 데이터를 파일로 박제(발행)할 이유가 대개 없다. 세그먼트·파라미터를 URL 에 인코딩해 공유하면 받는 쪽이 열 때 재계산한다. 스냅샷 발행은 "데이터가 재빌드로 바뀌어도 그때 값을 고정" 하고 싶을 때만 의미가 있는데, 이 맥락에선 드물어 **범위 밖**으로 둔다(`②↔③` 계약 `results.py` 는 코드에 남지만 대시보드는 부르지 않는다). |
| **단일/비교가 최상위 위계** | 비교는 특정 분석이 아니라 **모든 분석에 거는 연산**이다(스펙). 개요도 흐름도 행동도 전부 비교 가능하므로, `단일 | 비교` 가 분석 탭보다 위다. |
| **파라미터·표시 개수 전부 입력** | "상위 N 고정" 대신 사용자가 개수를 입력한다(최대치 안내, 슬라이더 없음). `path_ranking` 의 걸음 수 `n` 처럼 분석 파라미터도 전부 입력받는다. |

## 층 — 대시보드는 숫자를 만들지 않는다

```
analytics/analyses/   숫자 (이름 붙은 분석 12 + 연산자 3). 이미 존재.
        ↑
dashboard/            ★ 새 패키지. UI 전용. 계산 없음.
                      세그먼트→CubeSet 로드, 분석 호출, viz 렌더, URL 상태.
```

경계는 스펙 그대로다: **숫자를 만드는 코드는 `analyses/` 뿐**이고 대시보드는 그걸 부르고
그린다. 그래서 Claude 와 대시보드가 다른 답을 낼 수 없다.

## 위계·레이아웃

```
┌───────────────────────────────────────────────┐
│ [ 단일 | 비교 ]          ← 최상위 모드          │
├───────────────────────────────────────────────┤
│ 개요 · 화면흐름 · 행동 · 서비스 · 품질  ← 분석 탭 │
├──────────────┬────────────────────────────────┤
│ 사이드바      │ 메인                            │
│ ▤ 세그먼트    │ headline 카드 행                │
│  기간·서비스  │ ── 표시 개수 [N] (최대 M) ──    │
│  앱타입·버전  │ 표 (viz.x 기준)                 │
│  OS·성별·연령 │ 차트 (viz.kind)                 │
│  시간대       │ ⚠ 봉투 (경고·커버리지·사전·날짜) │
│ ── 분석 ▾     │                                │
│ ── 파라미터   │                                │
└──────────────┴────────────────────────────────┘
```

## 분석 탭 구성 (12개 배치)

| 탭 | 분석 |
|---|---|
| 개요 | `session_trend` |
| 화면흐름 | `screen_flow` · `screen_dwell_rank` · `screen_pair_affinity` · `reachability` · `screen_communities` |
| 행동 | `click_distribution` · `conditional_flow` · `path_ranking` · `markov_order_test` |
| 서비스 | `cross_service_flow` |
| 품질 | `quality_report` |

탭 안에서 분석이 여럿이면 사이드바 드롭다운으로 고른다.

## 사이드바 — 세그먼트 필터 (모든 탭 공통)

| 필터 | 위젯 | 기본값 | 비고 |
|---|---|---|---|
| 기간 | 날짜 범위 | 캐시에 있는 전체 | `present_dates` 에서 고른다 |
| 서비스 | 다중 선택 | 빌드된 전체 | **축이 아니라 빌드 범위** — 캐시된 조합만 |
| 앱타입 `service_type` | 드롭다운 | 전체 | MA/MW/PW |
| 버전·OS·성별·연령·시간대 | 드롭다운 | 전체 | `cubes.filter(축=값)` |

세션 큐브는 서비스로 못 가른다(44.7% 다중 서비스). 필터의 "서비스" 는 `load_cube_set` 의
빌드 범위 선택이고, 화면층 분석은 그 위에서 `service_type`·기타 축으로 좁힌다.

## 분석별 파라미터 (사이드바에 동적 표시)

선택한 분석에 맞는 파라미터 입력만 뜬다.

| 분석 | 파라미터 |
|---|---|
| `reachability` | `source`·`target`(화면 이름 선택)·`max_k` **(필수)** |
| `path_ranking` | `n` 걸음 수 **(필수)** |
| `click_distribution` | `by` (action_kind / layer1 / layer1,layer2) |
| `screen_flow` | `exit_within`·`damping` |
| `screen_dwell_rank` | `warn_below` |
| `screen_communities` | `seed`·`resolution` |
| `session_trend` | `holidays` (config 에서 자동) |
| `quality_report` | `thresholds` (config 에서 자동) |
| `screen_pair_affinity`·`conditional_flow`·`markov_order_test`·`cross_service_flow` | 없음 |

`reachability` 는 자기 루프(실측 최다 쌍이 `top/엠탑조회` 자기 루프)를 거부하므로,
`source`·`target` 선택지는 화면 목록에서 고르되 같은 값을 막는다.

## 표시 개수

표 위에 숫자 입력 하나. "최대 M 개까지" 안내(M = 그 분석 프레임 행 수). 슬라이더는 쓰지
않는다. 기본값은 10. `path_ranking`(고유 경로 수천~수만)·`screen_pair_affinity`(251쌍)처럼
큰 프레임에서 특히 쓰인다. headline·봉투는 개수와 무관하게 전부 보인다.

## 시각화 — 분석이 정한 `viz.kind` 를 따른다

대시보드는 계산을 안 하듯 **차트 종류도 발명하지 않는다.** `AnalysisResult.viz.kind` 를
읽어 4 종 렌더러 중 하나로 그린다. 표는 항상 함께 낸다.

| 분석 | `viz.kind` | `x` |
|---|---|---|
| `session_trend` · `reachability` · `quality_report` | **line** | period · k · period |
| `screen_flow` · `screen_dwell_rank` · `click_distribution` · `path_ranking` · `markov_order_test` | **bar** | state · state · screen · path · state |
| `screen_pair_affinity` · `conditional_flow` · `cross_service_flow` | **heatmap** | from_state · from_state · from_service |
| `screen_communities` | **graph** | state |

- **line**: x 축이 순서(날짜·걸음 k). 지표를 선으로.
- **bar**: x 항목별 막대. 표시 개수만큼 상위.
- **heatmap**: (from, to) 격자. 값은 cnt 또는 share.
- **graph**: 노드-엣지(Louvain 군집). `networkx` 의존이라 **우선순위 최저** — MVP 에선
  화면→군집 표 + `modularity` 로 대체하고 그래프 렌더는 뒤로 미룰 수 있다.

새 분석이 `viz.kind` 만 정하면 대시보드 수정 없이 렌더된다.

## 비교 모드

`단일 | 비교` 토글이 최상위. **비교**를 켜면 어느 탭이든 사이드바에 붙는다:

| 컨트롤 | 연산자 |
|---|---|
| 비교 축 `on` + `A`/`B` 값 (+ `released` 자동) | `compare` |
| 분해 축 `by` (선택) | `decompose` |
| "서비스별로 쪼개기" 체크 | `per_service` |

메인은 A/B 대조로 바뀐다: `pooled`(합산) · `per_day`(날짜별 + 물량) · `weight_skew` ·
`dates_used`(와 이유). 분해를 켜면 `within`·`between`·`per_stratum`·`composition`.
가드(날짜 겹침·배포일 컷오프·요일 대조)는 `compare` 안에 있으므로 대시보드는 그대로
받는다 — 스펙의 "가드는 연산자 한 곳" 원칙.

## 공유 — URL 상태

대시보드의 **모든 상태**를 URL query params 에 인코딩한다(`st.query_params`):

```
?mode=single&tab=flow&analysis=screen_flow
&dates=2026-07-14:2026-07-28&services=top&service_type=MA
&exit_within=1:3&top=10
```

- 상태가 바뀌면 URL 이 바뀐다. 공유 = **URL 복사**. 받는 쪽이 열면 그 세그먼트로 재계산.
- 비교 모드면 `mode=compare&on=app_version&a=9.5.1&b=9.5.0` 등이 붙는다.
- 인코딩/디코딩은 순수 함수(`state.py`)라 왕복 테스트로 고정한다.

## 봉투 표시

모든 결과 아래에 봉투를 편다 — 경고(예: `screens_lumped_into_other`)·커버리지·state
사전 버전·사용 날짜. 이게 "전수인지, 언제 데이터인지" 를 드러낸다. 발행이 없으니 봉투는
화면 표시로만 쓰인다 — 결과를 보는 사람이 늘 커버리지·날짜·사전 버전을 함께 본다.

## 파일 구조

```
dashboard/
  app.py           Streamlit 진입. 위계(단일/비교, 탭), URL 상태 배선
  state.py         URL query params ↔ 상태 dict (순수 함수, 왕복 테스트)
  filters.py       사이드바 세그먼트 필터 → load_cube_set + cubes.filter
  params.py        분석별 파라미터 위젯 (동적)
  render.py        AnalysisResult → headline 카드 + 표 + 차트 + 봉투
  charts.py        viz.kind 별 렌더러 (line/bar/heatmap/graph)
  compare_view.py  비교 모드 (compare/decompose/per_service 결과 렌더)
```

각 파일 단일 책임. 숫자는 전부 `analyses/` 호출, 대시보드 코드에 계산 로직 없음.

## 테스트 전략

- **`state.py` URL 왕복** — 상태 dict → URL → 상태 dict 가 항등. 1급 테스트(순수 함수).
- **`charts.py` viz.kind 매핑** — kind 별로 올바른 렌더러가 선택되는지 스모크.
- **분석 호출은 기존 테스트가 커버** — 대시보드는 `analyses/` 를 부르기만 하므로 숫자
  정확성은 `test_analyses_on_real_cubes.py` 등이 이미 지킨다.
- Streamlit UI 자체(위젯 배치·상호작용)는 자동 테스트가 어려워 수동 확인한다.

## 범위 밖 (안 함)

- **발행·저장** — URL 공유로 대체. `results.py` 계약은 코드에 남지만 대시보드는 안 부른다.
- **다중 사용자·권한** — 1인~소수, 로컬/간단 실행.
- **실시간·스트리밍** — 큐브는 날짜별 배치.
- **새 지표 자동 추가** — 새 분석은 사람이 코드로. `viz.kind` 만 정하면 대시보드가 렌더.

## 구현 범위 — 계획서 분할

전체가 한 계획서에 안 들어간다. 순서:

1. **골격 + 단일 모드**: `app`·`state`·`filters`·`params`·`render`·`charts`.
   12개 분석을 단일 모드로 렌더(line/bar/heatmap; graph 는 표로 대체). URL 상태. — 첫 계획서.
2. **비교 모드**: `compare_view` — `compare`·`decompose`·`per_service` 렌더. — 둘째 계획서.
3. **graph 렌더 + 다듬기**: `screen_communities` 그래프 시각화, 표시 개수·봉투 UX 정리.

첫 계획서의 종료 조건: 세그먼트를 골라 12개 분석을 단일 모드로 보고, URL 을 복사해 다시
열면 같은 화면이 재현된다.

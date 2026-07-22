# on-demand 디스크립티브 분석 스킬 설계 (Descriptive Analytics)

- 날짜: 2026-07-23
- 상태: 설계 확정 (구현 계획 대기)
- 범위: 서브프로젝트 **②의 첫 분석 스킬** — markov와 **분리된** 독립 스킬. `data_layer` 위에서 절대(전수) 지표를 계산해 `publish_result`로 발행한다. ②↔③ 경계 계약([2026-07-22-skill-platform-contract-design](2026-07-22-skill-platform-contract-design.md)) 위에 올라간다.

## 배경

roadmap 상 다음 단계는 "②a markov 스킬"이었으나, 착수 전 두 가지 요구가 확인됐다: (1) markov 파생 분석 외에 **기간별 UV/PV 같은 기본 지표**, (2) **앱 버전별 분리 분석**. 검토 결과 현재 구조(`query.run`은 분석 비종속 임의 SQL 실행, `column_map`에 `app_user_id`·`app_version`·`layer1~3`·`usage_duration` 등 이미 매핑됨)에서 **구조 변경 없이 가능**하며, 앞선 작업(①·②↔③ 계약)에 영향이 없음이 확인됐다.

단 하나의 설계 긴장: data_layer는 의도적으로 **seed-결정적 표본**을 캐시한다([sql_builder.build_prepare_sql](../../../data_layer/sql_builder.py)). 사용자는 **절대 지표**(대시보드용 실측값)를 원하므로, 표본 캐시로는 부족하고 **서버측 전수 집계**가 필요하다. 이는 markov의 표본 기반 분석과 병렬로 존재하는 별도 경로다.

## 관통 원칙

- 이 지표들은 markov에서 **파생된 게 아니라 독립적인 기술통계**다. markov 스킬의 하위 기능이 아니라 **형제격 독립 스킬**이다.
- **항상 자동 생성하지 않는다.** 사용자가 명명 지표를 파라미터로 **요청(on-demand)**할 때만 계산·발행한다. (roadmap의 미결 "선별 방식" → **요청형**으로 확정.)
- **절대 = 전수.** 표본이 아니라 전체 모집단을 서버측에서 집계한다. 결과는 작으므로 로컬에 캐시한다. 선례: [profile.fetch_action_counts](../../../data_layer/profile.py) (비샘플 서버 집계, `connect(source)` 직접 실행).
- **data_layer는 분석 비종속을 유지한다** (`query.run` docstring: "카운트+확률 등은 ②의 책임"). 따라서 지표 SQL·메뉴 semantics는 **스킬이 소유**하고, data_layer에는 범용 집계 프리미티브 하나만 추가한다.

## 스코프

**첫 배포 메뉴:**
- 기간별 UV·PV
- 세션수·체류시간
- 유저당 세션수·유저당 체류시간

**명시적 제외 (후속 on-demand):**
- 컴포넌트별 클릭·UV (`layer1/2/3` 기반) — 원래 요구가 "필요하다면"이었고 첫 메뉴에서 미선택
- 분포/히스토그램(유저당 지표의 평균만, 분포는 후속)
- gap(비활동 타임아웃) 기반 세션 — v1은 isuid 기반

**세션 정의:** `(app_user_id, isuid)` 쌍 = 1 세션. sessionization config = `{"method": "isuid"}`. 샘플링 코드([sql_builder.py](../../../data_layer/sql_builder.py)의 `session_meta`)가 이미 쓰는 grain과 동일. 나중에 gap 방식으로 바꾸면 `config_version`이 달라져 결과가 정확히 구분된다.

## 메뉴 (named analyses)

picked 3종을 **서버 스캔 최소화** 기준으로 2개 named analysis에 매핑한다. 세션수·체류시간(b)과 유저당 지표(c)는 동일 `GROUP BY`·동일 기반 카운트라 **한 번의 스캔**에서 모두 나온다.

### `uv_pv_by_period`
- columns: `[period, <breakdown…>, uv, pv]`
- `uv = COUNT(DISTINCT app_user_id)`
- `pv = COUNT(*) FILTER (WHERE action_type = 'Pageview')`

### `session_engagement_by_period`
- columns: `[period, <breakdown…>, sessions, total_duration, avg_duration_per_session, sessions_per_user, duration_per_user]`
- `sessions = COUNT(DISTINCT (app_user_id, isuid))`
- `total_duration = SUM(usage_duration)`
- `avg_duration_per_session = total_duration / sessions`
- `sessions_per_user = sessions / uv`  (uv = `COUNT(DISTINCT app_user_id)`)
- `duration_per_user = total_duration / uv`
- (유저당 = 평균. 분포는 후속.)

### 공통 파라미터
- `window`: `(start, end)` 날짜 경계
- `grain`: `{day, week, month}`, 기본 `day`. `date_trunc(grain, access_time)`로 period 버킷.
- `breakdown[]`: `⊆ {app_version, os, service_code}`, 기본 없음(전체 합계). 요구된 앱버전 분리는 `breakdown=["app_version"]`.
- `filters{}`: 화이트리스트 컬럼에 대한 단순 동등/IN 필터(선택).

### 비가산성 규칙 (correctness)
UV·세션수는 **비가산적**이다 — 일별 UV를 합쳐 월 UV를 만들 수 없다(중복 유저). 따라서 각 `grain`마다 **직접 집계 쿼리**를 돌린다(하위 grain 합산 금지). 이 규칙을 테스트로 못박는다.

## 컴포넌트 / 파일 구조

### data_layer (프리미티브 1개 추가만)
- `data_layer/fetch_aggregate.py` **(신규)**
  - `fetch_aggregate(config, source, sql, refresh=False) -> DataFrame`
  - `connect(source)`로 서버측 aggregate SQL을 **비샘플** 실행 → 결과를 `content_hash(sql, source.version())` 기반 parquet으로 `results_dir`에 캐시 → `manifest.add_result`로 색인. **성공 시에만** 캐시 기록. (캐시 키는 SQL+소스버전이 결정하므로 별도 key 파라미터 불필요.)
  - `refresh=True`면 캐시 무시하고 재실행.
- `data_layer/__init__.py`에 `fetch_aggregate` export.
- (선택적 후속) `profile.fetch_action_counts`를 `fetch_aggregate` 위로 리팩터링 — DRY. 이번 사이클에서는 건드리지 않는다.

### skills/descriptive/ (신규 패키지 — 지표 소유)
- `sql.py` — `build_uv_pv_sql(source, window, grain, breakdown, filters)`, `build_session_engagement_sql(...)`. 서버측 전수 집계 SQL 생성.
- `run.py` — `run_analysis(config, source, analysis_type, params) -> published_id`. 검증 → SQL 빌드 → `fetch_aggregate` → DataFrame shaping/반올림/유저당 파생 → `viz` 힌트 → `publish_result`.
- `descriptor.py` — 스킬 디스크립터(`name="descriptive"`, 메뉴·파라미터 스키마) 생성 + `register_skill` 호출.
- 위치: `skills/descriptive/` (향후 `skills/markov/`와 나란히). 최상위 `data_layer/`와 형제.

## 데이터 흐름

```
요청(analysis_type, params)
   │
   ▼ 스킬: 파라미터 검증 (Trino 치기 전)
   ▼ 스킬: aggregate SQL 빌드 (GROUP BY period+breakdown, 조건부 집계)
   ▼ data_layer.fetch_aggregate(config, source, sql)
        → Trino 전수 스캔 → 작은 결과 parquet 캐시 → manifest.results[] 색인
   ▼ 스킬: DataFrame shaping (rename/round, 유저당 파생), viz 힌트 부착
   ▼ publish_result(data, viz, params, config_version, caveats="전수집계(비샘플)")
        → <id>.parquet + <id>.json + manifest.published[]
   │
   ▼ ③ 플랫폼: list_results / read_result → 시각화 라이브러리로 렌더
```

- `viz` 힌트 예: `{"chart_type": "line", "encoding": {"x": "period", "y": ["uv", "pv"], "series": "app_version"}}`.
- `caveats`에 **"전수집계(비샘플)"** 를 명시해 markov의 표본 기반 결과와 구분한다.
- `config_version`: `config_version(dictionary, sessionization)`을 재사용하되, 디스크립티브 지표에 dictionary는 무관하므로 sessionization(`{"method":"isuid"}`)이 실질 결정 요소다.

## 에러 처리

- 파라미터 검증 실패 / 미지의 `analysis_type` → Trino 치기 **전에** `ValueError`(유효 메뉴 안내). 스캔 낭비 방지.
- 빈 결과(기간 내 데이터 없음) → 빈 결과 + `caveats="no data in window"`로 정상 발행. ③이 우아하게 "데이터 없음" 표시.
- Trino 연결/쿼리 실패 → 예외 전파, 부분 캐시 안 씀(성공 시에만 기록).
- breakdown·filters는 **고정 저카디널리티 화이트리스트**로만 허용 → 임의 group-by 없음 = 카디널리티 폭발 원천 차단(고정 메뉴형의 이점).

## 테스트 (TDD)

- `sql.py` 빌더 출력 형태 단위테스트 (`test_sql_builder.py` 방식: SQL 문자열/구조 assert).
- `fetch_aggregate` 캐시 동작: 2회차 재-fetch 없음, fake connection 주입.
- `run_analysis`: shaping 정확성 + `publish_result` 봉투(columns·viz·caveats) 정확성 — fake `fetch_aggregate`가 canned DataFrame 반환하도록 주입.
- 유저당 비율 계산 정확성(`sessions_per_user`, `duration_per_user`).
- 검증 에러 / 미지 analysis_type 경로.
- **UV 비가산성 가드 테스트**: grain별 재집계가 일어나는지(합산이 아닌지) 확인.
- 통합(선택, 기본 skip): 실 Trino aggregate 스모크 (`tests/integration/test_fetch_live.py` 방식).

## 성공 기준

- 사용자가 `run_analysis(config, source, "uv_pv_by_period", {window, grain, breakdown})` 한 번으로 계약 준수 결과(데이터+봉투+색인)를 발행할 수 있다.
- 앱 버전별 분리(`breakdown=["app_version"]`)가 재-fetch 없이 동작한다.
- 결과가 **절대(전수)** 값이며 `caveats`로 표본 기반 분석과 명확히 구분된다.
- data_layer에는 범용 `fetch_aggregate` 하나만 추가되고, 지표 정의는 전부 스킬에 있다(분석 비종속 경계 유지).
- ③이 `register_skill` 카탈로그에서 디스크립티브 스킬과 그 메뉴를 볼 수 있다.
- 새 지표 추가가 data_layer를 건드리지 않고 스킬 내에서 가능하다.

## 범위 밖 (별도 사이클)

- 컴포넌트별 클릭·UV, 분포/히스토그램, gap 기반 세션 — 후속 on-demand 메뉴 확장.
- markov 스킬(표본 기반 분석) — 별도 스펙/계획. 본 스킬과 형제.
- ③ 플랫폼 UI·시각화 라이브러리 — ②↔③ 계약을 소비하는 쪽. 별도 사이클.
- `profile.fetch_action_counts`의 `fetch_aggregate` 리팩터링 — 선택적 DRY 정리.

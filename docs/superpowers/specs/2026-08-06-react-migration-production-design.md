# 대시보드 React 전환 — 프로덕션 요구 개정 설계 (2026-08-06)

**한 줄**: Streamlit 대시보드를 **FastAPI(백엔드) + Vite·React·TypeScript·shadcn/ui·Tailwind(프론트)**
로 재구축한다. 숫자는 여전히 `analytics/analyses/` 만 만든다 — API 는 그걸 호출해 JSON 으로 낸다.
이 문서는 초안 `specs/2026-08-05-react-shadcn-migration-design.md`("로컬 dev 우선")를
**프로덕션 요구(공유용)에 맞게 개정·대체**한다.

## 배경 — 초안에서 무엇이 바뀌나

초안은 "로컬 dev 우선"이라 배포·인증·다중 사용자·메모리를 전부 "범위 밖"에 뒀다. 사용자 결정은
**완전 공유용 프로덕션**이므로, 아키텍처를 좌우하는 네 가지를 2026-08-06 브레인스토밍에서 확정했다.
바뀐 핵심은 **메모리 아키텍처**다 — 초안의 "큐브 전체를 프로세스에 상주"는 데이터가 커지면(1년치)
불가능하다고 계산으로 배제됐다(아래 근거).

**불변 원칙**: 숫자를 만드는 코드는 `analytics/analyses/` 뿐이다. 전환은 **표현 계층만** 바꾼다 —
분석·큐브·지표는 그대로. API 는 analyses 를 호출하는 얇은 배선이다.

## 확정된 결정 (2026-08-06 브레인스토밍)

| # | 결정 | 값 |
|---|---|---|
| 1 | **배포** | 개인 PC 사내망 공유(현행 유지). "프로덕션"은 결과물 품질(React+shadcn)을 뜻하며 배포 인프라가 아니다. 무거운 배포 파이프라인은 세우지 않는다. |
| 2 | **규모·인증** | 여러 팀이 보되 **인증 없음**. 사내망 신뢰 경계. API 를 가장 단순하게 유지. 대시보드는 집계 지표만 노출(개인 식별 정보 없음)이나 사내 트래픽 지표라 사내망 한정. |
| 3 | **메모리** | **선택 기간만 로드 + LRU 캐시 + 소프트 상한(한 달, 초과 허용+경고) + 절대 안전 상한(OOM 방어).** `analyses/` 불변, DuckDB 불필요. |
| 4 | **데이터 범위** | **표현계층 자동 적응** — `present_dates`/`present_services` 를 meta 로 노출, "지금 디스크에 있는 것"을 그대로 보여준다. **서비스는 전체 고정, 선택 UI 없음.** 빌드 파이프라인과 완전 독립. |

## 재조사 불필요한 실측 근거 (2026-08-06 확인)

메모리 아키텍처 결정의 근거다. 이 프로젝트의 지배적 실패 모드가 "그럴듯한데 틀린 숫자"라, 결정을
수치에 못박아 둔다.

| 항목 | 값 | 출처 |
|---|---|---|
| 이 맥 RAM | **36 GB** | `sysctl hw.memsize` |
| path 큐브 디스크 | 341M(두 빌드 버전 213M+129M), **하루 ~14 MB** | `du -sh cache/cubes/path` |
| path pandas 메모리 | 15일=~4 GB → **하루 ~267 MB** | project-roadmap 실측(1,929만 행) |
| path 로딩 | **15일 0.5초** → 한 달 ~1초 | 동상 |
| **한 달(31일) pandas** | **~8 GB** ✅ 36GB 단일 조회 여유 | 267MB×31 |
| **1년(365일) 전체 상주** | **~97 GB** ❌ 36GB 초과 = **불가능** | 267MB×365 |
| 1년 path 디스크 | ~4–5.5 GB ✅ 여유 | 14MB×365 |

→ **"큐브 전체 상주"(초안 발상)는 1년치에서 불가능.** 다행히 큐브가 이미 날짜별
`cache/cubes/{종류}/{sql_hash}/date=YYYY-MM-DD.parquet` 파일로 갈라져 있어 "고른 기간의 파일만
로드"가 자연스럽다. DuckDB 도 필요 없다 — pandas 가 선택된 날짜 파일만 읽으면 된다.

## 아키텍처 (개정)

```
analytics/analyses/   숫자 (16 분석 + 연산자 3). 그대로. ← 불변 원칙
        ↑ import (순수 함수/데이터만: charts·glossary·params)
api/                  ★ FastAPI. cube_store(로드/캐시/상한) → analyses 호출 → JSON
        ↑ HTTP (JSON)
frontend/             ★ Vite + React + TS + shadcn/ui + Tailwind
```

`dashboard/`(streamlit)는 **폐기**한다 — 순수 자산은 `api/` 로 이전해 살리고, `st` 위젯 코드만
제거한다(아래 "streamlit 폐기 계획").

## 백엔드 `api/` — 큐브 스토어가 핵심

```
api/
  main.py          FastAPI 앱, 라우팅, CORS(사내망)
  cube_store.py    ★ 신규. 날짜 파티션 parquet 로드 + LRU + 기간 상한
  meta.py          present_dates/services, 분석 카탈로그, params, glossary 조립
  analysis.py      요청 → cube_store → analyses 호출 → JSON 직렬화
  (charts.py·glossary.py·params.py  dashboard/ 에서 이전)
```

### `cube_store.py` 동작

- 요청 `(큐브종류, 기간[start,end], sql_hash)` → 그 **기간에 해당하는 날짜 parquet 파일만**
  `pd.read_parquet` 후 concat → `analyses/` 로 전달.
- **날짜 concat 만 한다.** 세그먼트/경로 조각 합산은 `analyses/`(예 `metrics/paths.py::top_paths`,
  `markov_order_test`)의 책임이며 이미 검증됐다 — cube_store 는 로드 범위만 파라미터화할 뿐,
  기존 dashboard 가 15일치를 한 번에 로드하던 것과 동일 동작이다(새 집계 함정 없음).
- 결과 프레임을 `functools.lru_cache`(maxsize 제한)로 캐시 — 같은 조회는 즉시, 오래된 건 evict.
  캐시 키는 `(종류, start, end, sql_hash)`. 읽기 전용 공유라 **동시 사용자가 늘어도 메모리 일정**.
- **소프트 상한(≈31일)**: 초과 요청도 처리하되 envelope 에 `period_wide` 경고를 첨부.
- **절대 상한(≈90일)**: 초과 시 400 + 메시지 — 경고를 무시한 거대 조회의 OOM 최후 방어선.
- **정본 빌드(sql_hash) 선택**: 디스크에 빌드 버전이 여럿일 수 있다(현재 6서비스 15일 `99f0…` /
  7서비스 9일 `d29d…`). meta 가 **정본 하나를 지정**한다 — 설정값 또는 "가장 날짜가 많은 완성본".
  `present_dates`/`present_services` 는 그 정본 기준이고, agorax 7서비스가 다 구워지면 정본을
  그쪽으로 전환한다. (당장은 완성본인 6서비스 15일이 정본.)

### 코드 재사용

`charts.py`(Altair→Vega-Lite `.to_dict()`)·`glossary.py`(한글 라벨)·`params.py`(파라미터 choices)는
이미 `st` 의존이 없는 순수 모듈이라 `api/` 로 **이전해 그대로 import** 한다. `st` 에 얽힌 배선·캐시·
위젯·URL 상태만 api/frontend 에서 새로 쓴다. **숫자 정확성 대조 기준은 streamlit UI 가 아니라
`tests/`(특히 `test_analyses_on_real_cubes.py`)에 있으므로**, streamlit 을 폐기해도 대조는 남는다.

## 프론트 `frontend/`

```
frontend/src/
  App.tsx        라우팅·URL 상태·레이아웃 조립 (header / body(sidebar+main))
  api.ts         fetch 래퍼 (/api/meta, /api/analysis)
  components/
    Header       전체폭 최상단: 로고 + [단일|비교] 탭 (비교 disabled = 3단계 자리)
    ControlBar   기간(DateRange) + 세그먼트 축 (아래 주의)
    Sidebar      분석 탭 + 분석 칩 + 파라미터 (얇게)
    ResultCards  headline → shadcn Card
    ResultChart  viz → react-vega (graph 는 초기 표 폴백)
    ResultTable  rows → shadcn Table + 클라이언트 페이지네이션
    Envelope     봉투 경고 (period_wide 등)
  lib/           shadcn utils, cn()
```

- **헤더가 진짜 전체폭 최상단** — 앱 최상위 flex 컬럼(header / body(sidebar+main)). streamlit
  제약(사이드바 전체높이)이 사라진다.
- shadcn/ui 는 `npx shadcn@latest init` 후 필요한 컴포넌트만 add.

### 세그먼트 축 주의 (설계에 못박음)

혼동하기 쉬운 두 개념을 분리한다.

- **서비스 scope**(top/media/search…) = 빌드 범위. **고정, 선택 UI 없음.** meta 의
  `present_services` 로 "지금 보는 범위"만 표시. 경로가 서비스를 넘나들어(전이의 ~50%가 서비스
  건너뜀) 전체를 한 덩어리로 본다.
- **`service_type` 축**(MA/MW/PW) = 세그먼트 축으로 **유지**. 위 scope 와 **다른 것**이다.
- 컨트롤바 세그먼트 축: `app_version · os · gender · age_band · daypart · service_type`(6개).
  서비스 scope 는 여기 없다.

### 기간 선택 UX

- `present_dates` 의 min~max 안에서 DateRange 선택. 기본 프리셋 = "마지막 빌드일 기준 한 달".
- **31일 초과 선택 시 인라인 경고 배지**("한 달 초과 — 느려질 수 있음").
- **절대 상한(~90일) 초과는 선택 자체를 막음**(백엔드 400 과 짝).

## API 계약

| 엔드포인트 | 반환 |
|---|---|
| `GET /api/meta` | `{ tabs, analyses:[{name,label,help,params,viz_kinds}], segments:[{axis,values}], present_dates:{min,max}, present_services, defaults }` |
| `GET /api/analysis/{name}` (query: `start,end,{axis}=…,{param}=…`) | `{ headline:[{label,value,help}], columns:[{key,label,help}], rows:[[]], viz:<VegaLite spec \| {kind:"graph",…}>, envelope:{warnings[], state_dict_version, n_dates, period_days} }` |

- 라벨(한글)·설명은 API 가 `glossary` 로 붙여 보낸다 — 프론트는 표시만.
- 필수 파라미터 누락 시 400 + 메시지. 절대 상한 초과 시 400. 소프트 상한 초과는 200 + `period_wide` 경고.
- **차트**: `charts.py` 의 Altair 가 이미 Vega-Lite 생성기다. `alt.Chart.to_dict()` 로 스펙을
  만들어 API 가 넘기면 프론트가 **react-vega** 로 렌더. graph(군집)는 Vega-Lite 밖이라 별도
  (초기엔 표, 이후 react 그래프 라이브러리).
- 페이지네이션: 초기엔 프론트가 전체 rows 를 받아 클라이언트 페이지네이션. 큰 프레임
  (path_ranking)은 이후 서버 페이지네이션으로 최적화(범위 밖).

## 상태 (URL 공유)

`?tab=flow&analysis=screen_flow&start=2026-07-14&end=2026-07-28&os=android&age_band=…&damping=0.85&page=1`
— React 가 URL query 를 읽어 초기 상태 시드, 상태 변화 시 `history.replaceState` 로 URL 갱신.
공유 = URL 복사(streamlit 과 동일 계약). `mode` 는 `single` 고정(비교는 3단계). 서비스 scope 는
고정이라 URL 에 없다.

## 구현 순서 (골격→점진)

1. **골격**:
   - `api/` FastAPI: `/api/meta` + `/api/analysis/{name}`(개요 `session_trend` 만 우선 연결) + cube_store.
   - `frontend/` scaffold: Vite+React+TS, Tailwind, shadcn init.
   - **Header(전체폭) + 기본 레이아웃** + 개요 분석 1개 렌더(카드·표·라인차트).
   - 로컬 dev: vite(5173) + fastapi(8000), vite proxy `/api` → 8000.
   - **종료 조건**: 브라우저에서 헤더가 최상단 전체폭으로 뜨고, 개요 분석이 카드·표·차트로 그려진다.
2. **컨트롤바·사이드바 완성**: 기간(한 달+경고)·세그먼트 축·탭·분석 칩·파라미터 드롭다운 전부.
3. **분석 점진 추가**: 나머지 15개 분석을 `viz.kind`(bar/line/heatmap/graph)별로 연결.
4. **다듬기 + streamlit 제거**: 페이지네이션 UX·반응형·graph 렌더·로딩/에러 상태 →
   **골격이 최소 동작(개요 분석 1개)한 걸 확인한 뒤** 순수모듈 이전 완료 + `dashboard/` 위젯 코드 제거.

각 단계 후 브라우저에서 확인·조정.

## streamlit 폐기 계획

- **이전(살림)**: `dashboard/charts.py`·`glossary.py`·`params.py` → `api/`. `state.py` 의 URL 왕복
  개념은 React 로 이전(코드는 새로 씀).
- **제거**: `dashboard/app.py`·`render.py`·`layout.py`·`state.py`(st 위젯 결합) → 삭제.
- **시점**: 구현 순서 4단계, api+react 골격 안정 확인 후. 전환 중 공백을 만들지 않는다.
- **안전망**: git 히스토리에 남아 필요 시 `git show` 로 참조. 숫자 대조는 `tests/` 가 계속 지킨다.

## 범위 밖 (당장 안 함)

- **비교 모드**(3단계, 기존 로드맵) — 헤더에 자리만.
- **배포/빌드 파이프라인** — 개인 PC 실행(현행).
- **인증·다중 사용자 접근 통제**.
- **서비스 선택 UI**(scope 필터축) — per_service 분석이 이미 서비스별 뷰를 준다.
- **agorax 큐브 빌드 재개**(7서비스 22일 중 9일에서 멈춤) — 별도 데이터 파이프라인 작업.
- **서버 페이지네이션** — 초기엔 클라이언트.

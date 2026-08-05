# 대시보드 React + shadcn 전환 설계 (2026-08-05)

**한 줄**: Streamlit 대시보드를 **FastAPI(백엔드) + Vite·React·TypeScript·shadcn/ui·Tailwind(프론트)**
로 재구축한다. 숫자는 여전히 `analytics/analyses/` 만 만든다 — API 는 그걸 호출해 JSON 으로 낸다.

## 배경 — 왜 전환하나

Streamlit 은 사이드바를 좌측 전체높이로 깔고 위젯을 세로로 쌓는 구조라, **전체폭 최상단 헤더**
같은 기본 레이아웃조차 CSS 해킹 없이는 어렵다. 컴포넌트 커스터마이즈(칩·탭·헤더)도 제약이 크다.
2026-08-05 결정: 프론트를 React + shadcn 으로 옮겨 레이아웃·컴포넌트를 100% 제어한다.

**불변 원칙**: 숫자를 만드는 코드는 `analytics/analyses/` 뿐이다. 전환은 **표현 계층만** 바꾼다 —
분석·큐브·지표는 그대로. API 는 analyses 를 호출하는 얇은 배선이다(streamlit `app.py` 가 하던 역할).

## 아키텍처

```
analytics/analyses/  숫자 (16 분석 + 연산자). 그대로.
        ↑ 호출
api/                 ★ FastAPI. analyses 호출 → JSON. 큐브 로드 캐시(서버 메모리).
        ↑ HTTP (JSON)
frontend/            ★ Vite + React + TS + shadcn/ui + Tailwind. 헤더·컨트롤바·사이드바·메인.
```

- **백엔드 `api/`**: FastAPI. 기존 `dashboard/` 의 배선 로직(세그먼트→큐브 로드→분석 호출,
  charts 의 Vega-Lite 생성, glossary 라벨)을 재사용/이식. 큐브는 프로세스 메모리에 캐시
  (streamlit `@st.cache_resource` 대응 — `functools.lru_cache` 또는 모듈 전역).
- **프론트 `frontend/`**: SPA. 상태는 URL query 로 공유(streamlit 과 동일 철학).
- **차트**: `charts.py` 의 Altair 는 이미 **Vega-Lite 생성기**다. `alt.Chart.to_dict()` 로
  Vega-Lite JSON 스펙을 만들어 API 가 넘기면, 프론트가 **react-vega** 로 렌더한다.
  graph(군집)는 Vega-Lite 가 아니라 별도(초기엔 표로, 이후 react 그래프 라이브러리).

## API 스펙 (초안)

| 엔드포인트 | 반환 |
|---|---|
| `GET /api/meta` | 탭 구조, 분석별 한글 라벨·설명, 파라미터 스펙(선택지 포함), 세그먼트 축·값, present_dates, 화면 목록 |
| `GET /api/analysis/{name}` (query: `start,end,{axis}=…,{param}=…`) | `{ headline: {label,value,help}[], columns: {key,label,help}[], rows: any[][], viz: <Vega-Lite spec \| {kind:"graph",...}>, envelope: {warnings,state_dict_version,n_dates} }` |

- 라벨(한글)·설명은 API 가 `glossary` 로 붙여 보낸다 — 프론트는 표시만.
- 필수 파라미터 누락 시 400 + 메시지.
- 페이지네이션: 프론트가 전체 rows 를 받아 클라이언트 페이지네이션(현재도 전량 로드). 큰 프레임
  (path_ranking)은 이후 서버 페이지네이션으로 최적화(초기 골격은 클라이언트).

## 프론트 구조 (컴포넌트)

```
frontend/src/
  App.tsx                 라우팅·URL 상태·레이아웃 조립
  api.ts                  fetch 래퍼 (/api/meta, /api/analysis)
  components/
    Header.tsx            전체폭 최상단: Markov 로고 + 단일/비교 탭(shadcn Tabs, 비교 disabled)
    ControlBar.tsx        기간(Date Select) + 세그먼트 축(shadcn Select/MultiSelect)
    Sidebar.tsx           분석 탭(shadcn Tabs) + 분석 칩(shadcn Toggle/Badge) + 파라미터(Select)
    ResultCards.tsx       headline → shadcn Card/Stat
    ResultChart.tsx       viz → react-vega (또는 graph 폴백)
    ResultTable.tsx       rows → shadcn Table + 페이지네이션
    Envelope.tsx          봉투 경고
  lib/                    shadcn utils, cn()
```

- **헤더가 진짜 전체폭 최상단** — 앱 최상위 flex 컬럼(header / body(sidebar+main)). streamlit
  제약이 사라진다.
- shadcn/ui 는 `npx shadcn@latest init` 로 설치, 필요한 컴포넌트만 add.

## 상태 (URL 공유)

`?mode=single&tab=flow&analysis=screen_flow&start=2026-07-14&end=2026-07-28&os=android&damping=0.85&page=1`
— React 가 URL query 를 읽어 초기 상태 시드, 상태 변화 시 `history.replaceState` 로 URL 갱신.
공유 = URL 복사(streamlit 과 동일 계약).

## 골격부터 점진 (실행 순서)

1. **골격**:
   - `api/` FastAPI: `/api/meta` + `/api/analysis/{name}` (개요 `session_trend` 만 우선 연결).
   - `frontend/` scaffold: Vite+React+TS, Tailwind, shadcn init.
   - **Header(전체폭) + 기본 레이아웃** + 개요 분석 1개 렌더(카드·표·라인차트).
   - 로컬 dev: vite(5173) + fastapi(8000), vite proxy `/api` → 8000.
   - **종료 조건**: 브라우저에서 헤더가 최상단 전체폭으로 뜨고, 개요 분석이 카드·표·차트로 그려진다.
2. **컨트롤바·사이드바 완성**: 기간·세그먼트·탭·분석 칩·파라미터 드롭다운 전부.
3. **분석 점진 추가**: 나머지 15개 분석을 viz.kind(bar/line/heatmap/graph)별로 연결.
4. **다듬기**: 페이지네이션 UX, 반응형, graph 렌더, 로딩/에러 상태.

각 단계 후 브라우저에서 확인·조정.

## 범위 밖 (당장 안 함)

- 배포/빌드 파이프라인 (로컬 dev 우선).
- 인증·다중 사용자.
- 비교 모드(3단계, 기존 로드맵) — 헤더에 자리만.
- 서버 페이지네이션 (초기엔 클라이언트).

## 기존 streamlit 대시보드

`dashboard/` 는 **참고용으로 남긴다**(삭제하지 않음). 배선 로직·charts·glossary·params 를
API 로 이식할 때 원본으로 쓴다. 안정화되면 이후 정리.

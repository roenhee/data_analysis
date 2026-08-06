# 프론트 골격 (1단계-B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vite+React+TS+shadcn/ui+Tailwind v4 프론트 골격을 세운다 — **전체폭 헤더**가 최상단에 뜨고,
1단계-A API(`/api/meta`, `/api/analysis/session_trend`)를 불러 **개요 분석(세션 추이)**을 지표 카드 ·
표 · **react-vega 라인차트**로 렌더한다. 컨트롤바·사이드바·나머지 분석은 2·3단계(별도).

**Architecture:** SPA. `api.ts` 가 1단계-A 백엔드(8000)를 `fetch` 하고, `App.tsx` 가 레이아웃
(header / main)을 조립한다. 골격은 컨트롤 위젯 없이 **개요 `session_trend` 하나**를 `present_dates`
전체 범위로 불러 렌더한다(기간·세그먼트 선택은 2단계). viz(Vega-Lite 스펙)는 react-vega `VegaLite`
컴포넌트가 렌더. 숫자는 여전히 백엔드 `analytics/analyses/` 만 만든다 — 프론트는 표시만.

**Tech Stack:** Vite, React 19, TypeScript, Tailwind CSS v4(`@tailwindcss/vite`), shadcn/ui(New York),
react-vega(+ vega, vega-lite). 패키지 매니저 **npm**(v11.8, node v24.13).

---

## 실행 노트 (엔지니어가 먼저 읽을 것)

- **작업 디렉토리**: 프론트는 `/Users/roen.axz-pc/Desktop/projects/data_analysis/frontend/`(이 계획에서 새로 만든다).
  루트는 `/Users/roen.axz-pc/Desktop/projects/data_analysis`.
- **백엔드가 떠 있어야 렌더가 보인다**: 1단계-A API 를 `/Users/roen.axz-pc/Desktop/projects/data_analysis`
  에서 `.venv/bin/uvicorn api.main:app --port 8000` 로 띄운다. vite dev 서버(5173)가 `/api` 를 8000 으로 proxy 한다.
- **검증은 브라우저 스모크가 주(主)다.** 프론트 골격의 종료조건은 "브라우저에서 보인다" 이므로,
  각 Task 뒤 `preview_start`(dev 서버)로 띄우고 `read_page`/`read_console_messages`/screenshot 으로
  확인한다. 자동 단위테스트는 순수 로직(`api.ts` 쿼리 조립)에만 최소로 둔다 — 컴포넌트 렌더는 브라우저로 본다.
- **shadcn init 은 대화형**일 수 있다. 기본값(New York style, Slate base color, CSS variables=yes)을
  수용한다. 막히면 `npx shadcn@latest init` 프롬프트에 기본값으로 답한다.
- **react-vega ↔ React 19 peer 경고 가능성**: 설치 시 peer dependency 경고가 나면
  `npm install react-vega vega vega-lite --legacy-peer-deps` 로 설치하고, 그래도 런타임 에러가 나면
  Task 5 의 대안(vega-embed 직접 호출) 노트를 따른다. **설치 직후 브라우저에서 차트가 실제로 그려지는지
  반드시 확인**하고 결과를 보고한다.
- **git**: master 브랜치, 사용자가 커밋 동의함. 각 Task 끝에 커밋한다. `frontend/node_modules` 는
  `frontend/.gitignore`(vite 가 생성)에 이미 포함되니 커밋되지 않는다.

## File Structure

```
frontend/
  package.json            vite 생성 + 의존성
  vite.config.ts          react + tailwindcss 플러그인, @ alias, /api proxy
  tsconfig.json           baseUrl/paths (@/*)
  tsconfig.app.json       baseUrl/paths (@/*)
  index.html              vite 생성
  components.json         shadcn 생성
  src/
    index.css             @import "tailwindcss"; + shadcn 변수(init 이 채움)
    main.tsx              vite 생성 (React 진입)
    App.tsx               ★ 레이아웃(header/main) + session_trend fetch·렌더
    api.ts                ★ fetch 래퍼 + 타입(Meta, AnalysisResult)
    lib/utils.ts          shadcn 생성 (cn())
    components/
      Header.tsx          ★ 전체폭: 로고 + 단일/비교 탭(비교 disabled)
      ResultCards.tsx     ★ headline → shadcn Card
      ResultTable.tsx     ★ columns/rows → shadcn Table (앞 50행)
      ResultChart.tsx     ★ viz → react-vega VegaLite (graph 는 안내 문구)
      ui/                 shadcn 생성 (card, table, tabs)
  src/api.test.ts         ★ api 쿼리 조립 단위테스트 (vitest, 최소)
```

`★` 가 이 계획에서 직접 작성하는 파일. 나머지는 CLI(vite/shadcn)가 생성한다.

---

## Task 1: Vite scaffold + Tailwind v4 + config

**Files:**
- Create (via CLI): `frontend/` 전체 (package.json, vite.config.ts, tsconfig*, index.html, src/*)
- Modify: `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/src/index.css`

- [ ] **Step 1: Vite React-TS 프로젝트 생성**

루트에서:
```bash
cd /Users/roen.axz-pc/Desktop/projects/data_analysis
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
```
Expected: `frontend/` 에 vite react-ts 스캐폴드 생성, 의존성 설치.

- [ ] **Step 2: Tailwind v4 설치**

`frontend/` 에서:
```bash
npm install tailwindcss @tailwindcss/vite
npm install -D @types/node
```

- [ ] **Step 3: `src/index.css` 를 Tailwind v4 로 교체**

`frontend/src/index.css` 전체를 다음으로 교체(기존 vite 기본 CSS 삭제):
```css
@import "tailwindcss";
```

- [ ] **Step 4: `vite.config.ts` — 플러그인·alias·proxy**

`frontend/vite.config.ts` 전체를 다음으로 교체:
```typescript
import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
})
```
(`@vitejs/plugin-react` 는 vite react-ts 템플릿이 이미 설치했다.)

- [ ] **Step 5: tsconfig 경로 alias**

`frontend/tsconfig.json` 의 `compilerOptions` 에 추가(없으면 `compilerOptions` 블록을 만들어):
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  }
}
```
`frontend/tsconfig.app.json` 의 `compilerOptions` 에도 같은 `baseUrl`/`paths` 두 줄을 추가한다(기존 옵션은 보존).

- [ ] **Step 6: dev 서버 스모크**

`preview_start` 로 dev 서버를 띄운다. 먼저 `.claude/launch.json` 이 없으면 만든다(루트에):
```json
{
  "version": "0.0.1",
  "configurations": [
    { "name": "frontend", "runtimeExecutable": "npm", "runtimeArgs": ["run", "dev", "--prefix", "frontend"], "port": 5173 }
  ]
}
```
그다음 `preview_start` `{name: "frontend"}`. 브라우저에서 vite 기본 페이지가 뜨고 콘솔 에러가 없는지 `read_console_messages` 로 확인.
Expected: vite 기본 페이지 렌더, Tailwind 로드(에러 없음).

- [ ] **Step 7: 커밋**

```bash
cd /Users/roen.axz-pc/Desktop/projects/data_analysis
git add frontend .claude/launch.json
git commit -m "feat(frontend): scaffold Vite+React+TS, Tailwind v4, /api proxy"
```

---

## Task 2: shadcn/ui init + 컴포넌트 추가

**Files:**
- Create (via CLI): `frontend/components.json`, `frontend/src/lib/utils.ts`, `frontend/src/components/ui/{card,table,tabs}.tsx`
- Modify: `frontend/src/index.css` (shadcn init 이 변수 추가)

- [ ] **Step 1: shadcn init**

`frontend/` 에서:
```bash
npx shadcn@latest init
```
대화형 프롬프트는 기본값 수용(New York, Slate, CSS variables). Tailwind v4 이므로 tailwind config 는 비워 둔다(init 이 알아서 처리). 완료 후 `src/lib/utils.ts`(cn())와 `components.json` 이 생기고 `src/index.css` 에 테마 변수가 추가된다.

- [ ] **Step 2: 골격에 필요한 컴포넌트 추가**

```bash
npx shadcn@latest add card table tabs
```
Expected: `src/components/ui/{card,table,tabs}.tsx` 생성. `@/components/ui/card` 등으로 import 가능.

- [ ] **Step 3: 스모크 — shadcn 컴포넌트가 렌더되는지**

`src/App.tsx` 를 임시로 Card 하나만 렌더하도록 바꿔 dev 서버에서 확인(Task 4 에서 전면 교체하므로 임시):
```tsx
import { Card, CardContent } from "@/components/ui/card"
export default function App() {
  return <Card><CardContent className="p-4">shadcn ok</CardContent></Card>
}
```
`preview_start`/reload 후 카드가 스타일과 함께 보이면 shadcn+Tailwind 연동 성공. 확인했으면 이 임시 코드는 Task 4 에서 교체된다.

- [ ] **Step 4: 커밋**

```bash
cd /Users/roen.axz-pc/Desktop/projects/data_analysis
git add frontend
git commit -m "feat(frontend): shadcn/ui init + card/table/tabs"
```

---

## Task 3: api.ts — fetch 래퍼 + 타입 (+ 단위테스트)

**Files:**
- Create: `frontend/src/api.ts`
- Create: `frontend/src/api.test.ts`
- Modify: `frontend/package.json` (vitest 스크립트 — 이미 없으면)

- [ ] **Step 1: vitest 설치**

`frontend/` 에서:
```bash
npm install -D vitest
```
`frontend/package.json` 의 `"scripts"` 에 `"test": "vitest run"` 을 추가.

- [ ] **Step 2: 쿼리 조립 실패 테스트 작성 (TDD)**

`frontend/src/api.test.ts`:
```typescript
import { describe, it, expect } from "vitest"
import { buildQuery } from "@/api"

describe("buildQuery", () => {
  it("sets scalar params and repeats array params", () => {
    const qs = buildQuery({ start: "2026-07-14", end: "2026-07-28", os: ["android", "ios"] })
    expect(qs.get("start")).toBe("2026-07-14")
    expect(qs.getAll("os")).toEqual(["android", "ios"])
  })
})
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd frontend && npm test`
Expected: FAIL — `buildQuery` not exported / module not found.

- [ ] **Step 4: api.ts 구현**

`frontend/src/api.ts`:
```typescript
// 1단계-A 백엔드 API 계약. 숫자는 백엔드 analyses 가 만든다 — 여기선 타입·fetch 만.

export interface ParamSpec {
  name: string
  kind: string
  required: boolean
  choices: string[]
}
export interface MetaAnalysis {
  name: string
  label: string
  help: string | null
  params: ParamSpec[]
}
export interface Meta {
  tabs: { key: string; label: string; analyses: string[] }[]
  analyses: MetaAnalysis[]
  segments: { axis: string; label: string; values: string[] }[]
  present_dates: string[]
  present_services: string[]
  defaults: { analysis: string; state_dict_version: string }
}

export interface Headline { label: string; value: string; help: string | null }
export interface Column { key: string; label: string; help: string | null }
export interface Envelope {
  warnings: string[]
  state_dict_version: string
  n_dates: number
  period_days: number | null
}
// Vega-Lite spec | { kind: "graph", ... } | null
export type Viz = Record<string, unknown> | null
export interface AnalysisResult {
  headline: Headline[]
  columns: Column[]
  rows: unknown[][]
  viz: Viz
  envelope: Envelope
}

const API = "/api"

/** 세그먼트 축은 반복(?os=a&os=b), 스칼라는 set. 백엔드 main.py 의 파싱과 짝. */
export function buildQuery(params: Record<string, string | string[]>): URLSearchParams {
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) value.forEach((v) => qs.append(key, v))
    else qs.set(key, value)
  }
  return qs
}

export async function fetchMeta(): Promise<Meta> {
  const r = await fetch(`${API}/meta`)
  if (!r.ok) throw new Error(`GET /api/meta → ${r.status}`)
  return r.json()
}

export async function fetchAnalysis(
  name: string,
  params: Record<string, string | string[]>,
): Promise<AnalysisResult> {
  const r = await fetch(`${API}/analysis/${name}?${buildQuery(params)}`)
  if (!r.ok) throw new Error(`GET /api/analysis/${name} → ${r.status}`)
  return r.json()
}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd frontend && npm test`
Expected: PASS (1 test).

- [ ] **Step 6: 커밋**

```bash
cd /Users/roen.axz-pc/Desktop/projects/data_analysis
git add frontend
git commit -m "feat(frontend): api.ts fetch wrappers + types + buildQuery test"
```

---

## Task 4: Header + App 레이아웃 (전체폭 헤더)

**Files:**
- Create: `frontend/src/components/Header.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Header 구현**

`frontend/src/components/Header.tsx`:
```tsx
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

/** 전체폭 최상단 헤더: Markov 로고 + 단일/비교 모드 탭(비교는 3단계라 비활성). */
export function Header() {
  return (
    <header className="w-full border-b px-6 py-3 flex items-center gap-6">
      <div
        className="text-2xl font-bold tracking-tight leading-none"
        style={{ fontFamily: "Georgia, 'Times New Roman', serif", color: "#4e79a7" }}
      >
        Markov<span style={{ color: "#f28e2b" }}>.</span>
      </div>
      <Tabs value="single">
        <TabsList>
          <TabsTrigger value="single">단일</TabsTrigger>
          <TabsTrigger value="compare" disabled title="비교 모드는 다음 단계에서 열립니다">
            비교
          </TabsTrigger>
        </TabsList>
      </Tabs>
    </header>
  )
}
```

- [ ] **Step 2: App 레이아웃 (header / main flex column)**

`frontend/src/App.tsx` 전체를 다음으로 교체(개요 렌더는 Task 5 에서 채우고, 지금은 헤더+빈 main):
```tsx
import { Header } from "@/components/Header"

export default function App() {
  return (
    <div className="flex flex-col min-h-screen">
      <Header />
      <main className="flex-1 p-6">
        <p className="text-muted-foreground">본문은 다음 단계에서 채웁니다.</p>
      </main>
    </div>
  )
}
```

- [ ] **Step 3: 브라우저 스모크 — 헤더 전체폭**

dev 서버 reload 후 `read_page`/screenshot: **헤더가 최상단 전체폭**으로 뜨고(로고 + 단일/비교 탭, 비교 비활성), main 이 그 아래에 있는지 확인. `read_console_messages` 로 에러 없음 확인.
Expected: 전체폭 헤더 + 아래 본문 영역.

- [ ] **Step 4: 커밋**

```bash
cd /Users/roen.axz-pc/Desktop/projects/data_analysis
git add frontend
git commit -m "feat(frontend): full-width Header + app layout"
```

---

## Task 5: 개요 분석 렌더 (카드·표·react-vega 차트)

**Files:**
- Create: `frontend/src/components/ResultCards.tsx`, `ResultTable.tsx`, `ResultChart.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: react-vega 설치**

`frontend/` 에서:
```bash
npm install react-vega vega vega-lite
```
peer 경고가 나면 `--legacy-peer-deps` 를 붙여 재설치. (React 19 호환 확인은 Step 5 브라우저에서.)

- [ ] **Step 2: ResultCards**

`frontend/src/components/ResultCards.tsx`:
```tsx
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import type { Headline } from "@/api"

export function ResultCards({ headline }: { headline: Headline[] }) {
  if (!headline.length) return null
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {headline.map((h) => (
        <Card key={h.label}>
          <CardHeader className="pb-1">
            <CardTitle
              className="text-sm font-normal text-muted-foreground"
              title={h.help ?? undefined}
            >
              {h.label}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{h.value}</CardContent>
        </Card>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: ResultTable (앞 50행)**

`frontend/src/components/ResultTable.tsx`:
```tsx
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table"
import type { Column } from "@/api"

/** 골격은 앞 50행만. 페이지네이션은 2단계. */
export function ResultTable({ columns, rows }: { columns: Column[]; rows: unknown[][] }) {
  const page = rows.slice(0, 50)
  return (
    <div className="rounded-md border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((c) => (
              <TableHead key={c.key} title={c.help ?? undefined}>{c.label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.map((row, i) => (
            <TableRow key={i}>
              {row.map((cell, j) => (
                <TableCell key={j}>{cell == null ? "" : String(cell)}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
```

- [ ] **Step 4: ResultChart (react-vega)**

`frontend/src/components/ResultChart.tsx`:
```tsx
import { VegaLite } from "react-vega"
import type { Viz } from "@/api"

/** viz 가 Vega-Lite 스펙이면 렌더. graph(군집)는 다음 단계라 안내만. */
export function ResultChart({ viz }: { viz: Viz }) {
  if (!viz) return null
  if ((viz as { kind?: string }).kind === "graph") {
    return <div className="text-sm text-muted-foreground">그래프 뷰는 다음 단계에서 렌더됩니다.</div>
  }
  return (
    <div className="w-full overflow-x-auto">
      <VegaLite spec={viz as Record<string, unknown>} actions={false} />
    </div>
  )
}
```
**대안(react-vega 가 React 19 에서 렌더 실패 시):** `react-vega` 를 지우고 `vega-embed` 를 직접 쓴다 —
`npm install vega-embed`, 그리고 ResultChart 를 `useRef`+`useEffect` 로 `import embed from "vega-embed"; embed(ref.current, spec, {actions:false})` 하도록 바꾼다. 어느 쪽이든 **차트가 실제로 그려지는지 브라우저에서 확인**하고 보고.

- [ ] **Step 5: App 에 개요 렌더 연결**

`frontend/src/App.tsx` 전체를 다음으로 교체:
```tsx
import { useEffect, useState } from "react"
import { Header } from "@/components/Header"
import { ResultCards } from "@/components/ResultCards"
import { ResultTable } from "@/components/ResultTable"
import { ResultChart } from "@/components/ResultChart"
import { fetchMeta, fetchAnalysis, type AnalysisResult } from "@/api"

export default function App() {
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      try {
        const meta = await fetchMeta()
        const dates = meta.present_dates
        if (!dates.length) throw new Error("present_dates 가 비어 있습니다")
        const start = dates[0]
        const end = dates[dates.length - 1]
        setResult(await fetchAnalysis("session_trend", { start, end }))
      } catch (e) {
        setError(String(e))
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  return (
    <div className="flex flex-col min-h-screen">
      <Header />
      <main className="flex-1 p-6 space-y-4">
        {loading && <p className="text-muted-foreground">로딩 중…</p>}
        {error && <p className="text-red-600">에러: {error}</p>}
        {result && (
          <>
            <h2 className="text-lg font-semibold">개요 · 세션 추이</h2>
            <ResultCards headline={result.headline} />
            <ResultChart viz={result.viz} />
            <ResultTable columns={result.columns} rows={result.rows} />
          </>
        )}
      </main>
    </div>
  )
}
```

- [ ] **Step 6: 통합 브라우저 검증 (종료조건)**

**백엔드를 먼저 띄운다**(루트에서): `.venv/bin/uvicorn api.main:app --port 8000` (백그라운드). 그다음 dev
서버(`preview_start` `{name:"frontend"}`) reload. 브라우저에서 확인:
- 헤더가 전체폭 최상단.
- "개요 · 세션 추이" 아래 **지표 카드**(세션 수 등), **라인차트**(period 축), **표**(앞 50행)가 보인다.
- `read_console_messages` 에러 없음. `read_network_requests` 로 `/api/meta`·`/api/analysis/session_trend` 가 200 인지 확인.
- screenshot 으로 최종 상태 기록.
Expected: 전체폭 헤더 + session_trend 카드·차트·표가 실데이터로 렌더.

- [ ] **Step 7: 커밋**

```bash
cd /Users/roen.axz-pc/Desktop/projects/data_analysis
git add frontend
git commit -m "feat(frontend): render overview (session_trend) — cards, react-vega chart, table"
```

---

## Self-Review

**1. Spec coverage** (spec 2026-08-06 "구현 순서 1. 골격" + "프론트 구조"):
- Vite+React+TS+shadcn+Tailwind scaffold → Task 1·2 ✅
- 전체폭 헤더(header / body flex) → Task 4 ✅
- api.ts fetch 래퍼(/api/meta, /api/analysis) → Task 3 ✅
- 개요 분석 1개(session_trend) 카드·표·차트 렌더 → Task 5 ✅
- react-vega 로 viz 렌더 → Task 5 (ResultChart) ✅
- vite(5173)+fastapi(8000) proxy → Task 1 (vite.config server.proxy) ✅
- **종료조건**(헤더 전체폭 + 개요 카드·표·차트) → Task 5 Step 6 브라우저 검증 ✅
- **범위 밖(이 계획)**: 컨트롤바·사이드바(기간·세그먼트·탭·칩·파라미터) = 2단계, 나머지 15개 분석 = 3단계,
  URL 상태 왕복 = 2단계(골격은 present_dates 기본 범위 하드코딩), 페이지네이션 UX·graph 렌더 = 4단계.

**2. Placeholder scan:** "TBD/TODO" 없음. 모든 컴포넌트·설정 코드 완전. scaffold 는 CLI 생성이라
명령으로 대체(정확한 명령 제공).

**3. Type consistency:**
- `api.ts` 의 `Meta`/`AnalysisResult` 는 1단계-A 응답 형태와 일치: `/api/meta` = `{tabs, analyses, segments,
  present_dates(list), present_services, defaults}`(스펙 개정 반영 — present_dates 는 list, analyses 에
  viz_kinds 없음), `/api/analysis` = `{headline, columns, rows, viz, envelope}`.
- `buildQuery` 의 반복-쿼리 규약이 백엔드 `main.py` 의 `getlist(axis)` 파싱과 짝(골격에선 세그먼트 미사용이나 계약 일치).
- `ResultChart` 가 `viz.kind === "graph"` 분기 — 백엔드 `analysis.vega_spec` 이 graph 를 passthrough 로 내는 것과 일치.
- 컴포넌트 import 경로 `@/components/...`, `@/api` — Task 1 의 alias 설정과 일치.

**4. 검증 방식 주의(프론트 특성):** 이 계획은 백엔드와 달리 **브라우저 스모크가 주 검증**이다. 순수 로직
(`buildQuery`)만 vitest, 컴포넌트·레이아웃·차트는 `preview` 로 실물 확인한다. subagent 실행 시 각 Task 의
브라우저 스텝을 건너뛰지 말 것 — "코드가 컴파일된다" 는 "화면에 보인다" 가 아니다. react-vega ↔ React 19
호환은 Task 5 Step 4·6 에서 실제 렌더로만 판정한다(설치 성공 ≠ 렌더 성공).

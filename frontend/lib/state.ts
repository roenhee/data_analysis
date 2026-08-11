// 대시보드 상태 + URL 공유. Next 라우터 API 를 쓰지 않고(AGENTS.md: Next 16 은 training 과
// 다르다) 순수 함수로 URL query ↔ 상태를 오간다. page.tsx 가 window.history.replaceState 로
// URL 을 갱신하고, 최초 진입 시 window.location.search 로 시드한다.

import type { Meta } from "@/lib/api"

export interface DashState {
  tab: string
  analysis: string
  start: string
  end: string
  segments: Record<string, string[]> // 세그먼트 축 → 선택 값들(다중, 빈 배열=전체)
  params: Record<string, string> // 분석 파라미터 → 값
  page: number
}

// tab·analysis·start·end·page 는 프론트 상태다. 세그먼트 축과 파라미터는 백엔드로도 간다.
const RESERVED = new Set(["tab", "analysis", "start", "end", "page"])

/** 어떤 분석이 어느 탭에 속하는지. 없으면 첫 탭. */
export function tabOfAnalysis(meta: Meta, analysis: string): string {
  const hit = meta.tabs.find((t) => t.analyses.includes(analysis))
  return hit ? hit.key : meta.tabs[0]?.key ?? "overview"
}

/** 분석의 파라미터를 기본값으로 채운다 — 필수 파라미터가 비면 백엔드가 400 이라, 고르기
 *  전에도 바로 돌아가게 한다. 이미 있는 값은 보존한다.
 *  kind="screen"(reachability 의 source/target)은 choices 가 없어 present_screens 에서
 *  순서대로(첫 화면·둘째 화면) 채운다 — 둘이 같으면 "already on" 에러라 반드시 다르게. */
export function defaultParams(
  meta: Meta,
  analysis: string,
  existing: Record<string, string> = {},
): Record<string, string> {
  const spec = meta.analyses.find((a) => a.name === analysis)
  const out: Record<string, string> = {}
  let screenN = 0
  for (const p of spec?.params ?? []) {
    const fallback =
      p.kind === "screen"
        ? meta.present_screens[screenN] ?? ""
        : String(p.choices[0] ?? "")
    if (p.kind === "screen") screenN++
    out[p.name] = existing[p.name] ?? fallback
  }
  return out
}

/** end 에서 한 달 뒤로 물러난 start(빌드된 첫날 밑으로는 안 내려감). */
function oneMonthBack(start: string, end: string): string {
  const d = new Date(end + "T00:00:00Z")
  d.setUTCMonth(d.getUTCMonth() - 1)
  const back = d.toISOString().slice(0, 10)
  return back < start ? start : back
}

/** meta + (선택적)URL 로 초기 상태를 만든다. URL 값이 있으면 우선, 없으면 기본. */
export function initialState(meta: Meta, search: string): DashState {
  const q = new URLSearchParams(search)
  const dates = meta.present_dates
  const first = dates[0]
  const last = dates[dates.length - 1]

  const analysis = q.get("analysis") ?? meta.defaults.analysis
  const tab = q.get("tab") ?? tabOfAnalysis(meta, analysis)
  const end = q.get("end") ?? last
  const start = q.get("start") ?? oneMonthBack(first, end)

  const segments: Record<string, string[]> = {}
  for (const s of meta.segments) {
    const vals = q.getAll(s.axis)
    if (vals.length) segments[s.axis] = vals
  }

  const params: Record<string, string> = {}
  const axisNames = new Set(meta.segments.map((s) => s.axis))
  for (const [k, v] of q.entries()) {
    if (!RESERVED.has(k) && !axisNames.has(k)) params[k] = v
  }
  const withDefaults = defaultParams(meta, analysis, params)

  const page = Math.max(1, Number(q.get("page") ?? "1") || 1)
  return { tab, analysis, start, end, segments, params: withDefaults, page }
}

/** 상태 → URL query 문자열(공유용). 세그먼트는 반복 키, 파라미터는 key=value. */
export function toQuery(state: DashState): string {
  const q = new URLSearchParams()
  q.set("tab", state.tab)
  q.set("analysis", state.analysis)
  q.set("start", state.start)
  q.set("end", state.end)
  for (const [axis, vals] of Object.entries(state.segments)) {
    for (const v of vals) q.append(axis, v)
  }
  for (const [name, value] of Object.entries(state.params)) {
    if (value !== "") q.set(name, value)
  }
  if (state.page > 1) q.set("page", String(state.page))
  return q.toString()
}

/** 분석 요청에 보낼 파라미터만(백엔드 계약: start·end·세그먼트 반복·파라미터). tab·page 는
 *  프론트 상태라 제외한다. */
export function toFetchParams(state: DashState): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {
    start: state.start,
    end: state.end,
  }
  for (const [axis, vals] of Object.entries(state.segments)) {
    if (vals.length) out[axis] = vals
  }
  for (const [name, value] of Object.entries(state.params)) {
    if (value !== "") out[name] = value
  }
  return out
}

export const SOFT_LIMIT_DAYS = 31
export const HARD_LIMIT_DAYS = 90

/** [start,end] 양끝 포함 일수. */
export function periodDays(start: string, end: string): number {
  const a = new Date(start + "T00:00:00Z").getTime()
  const b = new Date(end + "T00:00:00Z").getTime()
  return Math.round((b - a) / 86_400_000) + 1
}

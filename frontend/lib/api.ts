// 1단계-A 백엔드 API 계약. 숫자는 백엔드 analyses 가 만든다 — 여기선 타입·fetch 만.
// 백엔드(FastAPI)는 CORS 를 열어 두므로(allow_origins=["*"]) 직접 호출한다.
// 배포 시 NEXT_PUBLIC_API_BASE 로 백엔드 주소를 바꾼다(기본 dev = localhost:8000).

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
  present_screens: string[]
  defaults: { analysis: string; state_dict_version: string }
}

export interface Headline {
  label: string
  value: string
  help: string | null
}
export interface Column {
  key: string
  label: string
  help: string | null
}
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

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"
const API = `${BASE}/api`

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

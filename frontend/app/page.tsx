"use client"

import { useEffect, useMemo, useState } from "react"
import { Header } from "@/components/Header"
import { Sidebar } from "@/components/Sidebar"
import { ControlBar } from "@/components/ControlBar"
import { ResultCards } from "@/components/ResultCards"
import { ResultTable } from "@/components/ResultTable"
import { ResultChart } from "@/components/ResultChart"
import { Envelope } from "@/components/Envelope"
import {
  buildQuery,
  fetchAnalysis,
  fetchMeta,
  type AnalysisResult,
  type Meta,
} from "@/lib/api"
import {
  type DashState,
  HARD_LIMIT_DAYS,
  initialState,
  periodDays,
  toFetchParams,
  toQuery,
} from "@/lib/state"

export default function Home() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [dash, setDash] = useState<DashState | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fetching, setFetching] = useState(false)

  // 최초: meta 로드 → URL + meta 로 초기 상태 시드.
  useEffect(() => {
    ;(async () => {
      try {
        const m = await fetchMeta()
        setMeta(m)
        setDash(initialState(m, window.location.search))
      } catch (e) {
        setError(String(e))
      }
    })()
  }, [])

  // 컨트롤 변경은 page 를 1 로 되돌린다(자기 자신 변경은 예외).
  function update(patch: Partial<DashState>) {
    setDash((prev) =>
      prev ? { ...prev, page: 1, ...patch } : prev,
    )
  }

  // 분석 요청에 실제로 영향을 주는 부분만 키로 삼아, page/tab 변경으로는 재조회하지 않는다.
  const fetchKey = useMemo(
    () =>
      dash ? `${dash.analysis}?${buildQuery(toFetchParams(dash))}` : null,
    [dash],
  )

  const overHard = dash ? periodDays(dash.start, dash.end) > HARD_LIMIT_DAYS : false

  // URL 은 dash 전체를 따른다(page 변경도 공유되게) — fetch 트리거와 분리한다.
  const query = dash ? toQuery(dash) : null
  useEffect(() => {
    if (query != null) window.history.replaceState(null, "", `?${query}`)
  }, [query])

  // fetchKey 가 바뀔 때만 재조회한다(page/tab 변경으로는 조회 안 함).
  useEffect(() => {
    if (!dash || !meta) return
    if (overHard) {
      setError(`기간이 ${HARD_LIMIT_DAYS}일을 넘습니다 — 좁혀서 조회하세요`)
      setResult(null)
      return
    }
    let cancelled = false
    setFetching(true)
    setError(null)
    ;(async () => {
      try {
        const r = await fetchAnalysis(dash.analysis, toFetchParams(dash))
        if (!cancelled) setResult(r)
      } catch (e) {
        if (!cancelled) {
          setError(String(e))
          setResult(null)
        }
      } finally {
        if (!cancelled) setFetching(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // fetchKey 로 조회 트리거(page/tab 변경은 제외). URL 갱신은 dash 전체를 따른다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchKey])

  const analysisLabel =
    meta?.analyses.find((a) => a.name === dash?.analysis)?.label ?? dash?.analysis
  const tabLabel = meta?.tabs.find((t) => t.key === dash?.tab)?.label

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      {!meta || !dash ? (
        <main className="flex-1 p-6">
          {error ? (
            <p className="text-red-600">에러: {error}</p>
          ) : (
            <p className="text-muted-foreground">로딩 중…</p>
          )}
        </main>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <Sidebar meta={meta} state={dash} onChange={update} />
          <div className="flex min-w-0 flex-1 flex-col">
            <ControlBar meta={meta} state={dash} onChange={update} />
            <main className="flex-1 space-y-4 overflow-auto p-6">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">
                  {tabLabel} · {analysisLabel}
                </h2>
                {fetching && (
                  <span className="text-sm text-muted-foreground">불러오는 중…</span>
                )}
              </div>
              {error && <p className="text-red-600">에러: {error}</p>}
              {result && (
                <>
                  <Envelope envelope={result.envelope} />
                  <ResultCards headline={result.headline} />
                  <ResultChart
                    viz={result.viz}
                    columns={result.columns}
                    rows={result.rows}
                  />
                  <ResultTable
                    columns={result.columns}
                    rows={result.rows}
                    page={dash.page}
                    onPageChange={(p) => update({ page: p })}
                  />
                </>
              )}
            </main>
          </div>
        </div>
      )}
    </div>
  )
}

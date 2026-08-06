"use client"

import { useEffect, useState } from "react"
import { Header } from "@/components/Header"
import { ResultCards } from "@/components/ResultCards"
import { ResultTable } from "@/components/ResultTable"
import { ResultChart } from "@/components/ResultChart"
import { fetchMeta, fetchAnalysis, type AnalysisResult } from "@/lib/api"

export default function Home() {
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

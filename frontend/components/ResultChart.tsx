"use client"

import { useEffect, useState } from "react"
import { VegaEmbed } from "react-vega"
import type { Column, Viz } from "@/lib/api"
import { GraphChart } from "@/components/GraphChart"

/** viz 가 Vega-Lite 스펙이면 VegaEmbed 로, graph(군집)면 GraphChart(force-directed)로 렌더.
 * react-vega 는 VegaEmbed 컴포넌트를 export 하고(vega-embed 래퍼) Vega-Lite 스펙도 렌더한다.
 * 브라우저 전용이라 mount 후에만 렌더한다(SSR 안전). */
export function ResultChart({
  viz,
  columns,
  rows,
}: {
  viz: Viz
  columns: Column[]
  rows: unknown[][]
}) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  if (!mounted || !viz) return null
  if ((viz as { kind?: string }).kind === "graph") {
    const edges = ((viz as { edges?: [string, string, number][] }).edges ?? [])
    return <GraphChart edges={edges} columns={columns} rows={rows} />
  }
  return (
    <div className="w-full overflow-x-auto">
      <VegaEmbed spec={viz as Record<string, unknown>} options={{ actions: false }} />
    </div>
  )
}

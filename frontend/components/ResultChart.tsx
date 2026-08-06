"use client"

import { useEffect, useState } from "react"
import { VegaEmbed } from "react-vega"
import type { Viz } from "@/lib/api"

/** viz 가 Vega-Lite 스펙이면 렌더. graph(군집)는 다음 단계라 안내만.
 * react-vega 는 VegaEmbed 컴포넌트를 export 하고(vega-embed 래퍼) Vega-Lite 스펙도 렌더한다.
 * 브라우저 전용이라 mount 후에만 렌더한다(SSR 안전). */
export function ResultChart({ viz }: { viz: Viz }) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  if (!mounted || !viz) return null
  if ((viz as { kind?: string }).kind === "graph") {
    return <div className="text-sm text-muted-foreground">그래프 뷰는 다음 단계에서 렌더됩니다.</div>
  }
  return (
    <div className="w-full overflow-x-auto">
      <VegaEmbed spec={viz as Record<string, unknown>} options={{ actions: false }} />
    </div>
  )
}

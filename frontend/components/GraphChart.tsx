"use client"

import { useEffect, useMemo, useState } from "react"
import { VegaEmbed } from "react-vega"
import type { Column } from "@/lib/api"

/** 군집 그래프(screen_communities): viz.edges + 프레임의 state→community 로 force-directed
 *  네트워크를 그린다. Vega(Vega-Lite 아님)의 force 트랜스폼을 쓴다 — vega 는 이미 의존이라
 *  새 라이브러리가 필요 없다. Streamlit 의 graphviz_chart 대응품(노드 색=군집). */
export function GraphChart({
  edges,
  columns,
  rows,
}: {
  edges: [string, string, number][]
  columns: Column[]
  rows: unknown[][]
}) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const spec = useMemo(() => {
    const stateIdx = columns.findIndex((c) => c.key === "state")
    const commIdx = columns.findIndex((c) => c.key === "community")
    const degIdx = columns.findIndex((c) => c.key === "degree")
    if (stateIdx < 0 || commIdx < 0) return null

    const nodes = rows.map((r) => ({
      name: String(r[stateIdx]),
      group: Number(r[commIdx]),
      degree: degIdx >= 0 ? Number(r[degIdx]) : 1,
    }))
    const indexOf = new Map(nodes.map((n, i) => [n.name, i]))
    const links = edges
      .filter(([u, v]) => indexOf.has(u) && indexOf.has(v))
      .map(([u, v, w]) => ({
        source: indexOf.get(u)!,
        target: indexOf.get(v)!,
        weight: w,
      }))

    return {
      $schema: "https://vega.github.io/schema/vega/v5.json",
      width: 720,
      height: 480,
      padding: 0,
      autosize: "none",
      signals: [
        { name: "cx", update: "width / 2" },
        { name: "cy", update: "height / 2" },
        { name: "nodeRadius", value: 9 },
        { name: "nodeCharge", value: -45 },
        { name: "linkDistance", value: 55 },
        { name: "static", value: true },
      ],
      scales: [
        {
          name: "color",
          type: "ordinal",
          domain: { data: "node-data", field: "group" },
          range: { scheme: "tableau10" },
        },
        {
          name: "size",
          type: "sqrt",
          domain: { data: "node-data", field: "degree" },
          range: [80, 900],
        },
      ],
      data: [
        { name: "node-data", values: nodes },
        { name: "link-data", values: links },
      ],
      marks: [
        {
          name: "links",
          type: "path",
          from: { data: "link-data" },
          interactive: false,
          encode: {
            update: {
              stroke: { value: "#cbd5e1" },
              strokeWidth: { value: 1 },
            },
          },
          transform: [
            {
              type: "linkpath",
              require: { signal: "force" },
              shape: "line",
              sourceX: "datum.source.x",
              sourceY: "datum.source.y",
              targetX: "datum.target.x",
              targetY: "datum.target.y",
            },
          ],
        },
        {
          name: "nodes",
          type: "symbol",
          zindex: 1,
          from: { data: "node-data" },
          encode: {
            enter: {
              fill: { scale: "color", field: "group" },
              stroke: { value: "white" },
              strokeWidth: { value: 1 },
              tooltip: {
                signal:
                  "{'화면': datum.name, '군집': datum.group, '연결도': datum.degree}",
              },
            },
            update: {
              size: { scale: "size", field: "degree" },
              x: { field: "x" },
              y: { field: "y" },
            },
          },
          transform: [
            {
              type: "force",
              iterations: 300,
              static: { signal: "static" },
              signal: "force",
              forces: [
                { force: "center", x: { signal: "cx" }, y: { signal: "cy" } },
                { force: "collide", radius: { signal: "nodeRadius" } },
                { force: "nbody", strength: { signal: "nodeCharge" } },
                {
                  force: "link",
                  links: "link-data",
                  distance: { signal: "linkDistance" },
                },
              ],
            },
          ],
        },
        {
          type: "text",
          from: { data: "nodes" },
          interactive: false,
          encode: {
            update: {
              x: { field: "x" },
              y: { field: "y", offset: -13 },
              text: { field: "datum.name" },
              align: { value: "center" },
              fontSize: { value: 9 },
              fill: { value: "#475569" },
            },
          },
        },
      ],
    } as Record<string, unknown>
  }, [edges, columns, rows])

  if (!mounted || !spec) return null
  return (
    <div className="w-full overflow-x-auto rounded-md border p-2">
      <VegaEmbed spec={spec} options={{ actions: false }} />
    </div>
  )
}

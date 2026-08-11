"use client"

import type { Meta } from "@/lib/api"
import { type DashState, defaultParams, tabOfAnalysis } from "@/lib/state"

/** 좌측 사이드바: 분석 탭 → 탭별 분석 칩 → 선택 분석의 파라미터.
 *  탭·칩을 바꾸면 그 분석의 파라미터를 기본값으로 새로 채운다(필수 파라미터 400 회피). */
export function Sidebar({
  meta,
  state,
  onChange,
}: {
  meta: Meta
  state: DashState
  onChange: (patch: Partial<DashState>) => void
}) {
  const currentTab =
    meta.tabs.find((t) => t.key === state.tab) ?? meta.tabs[0]

  function pickTab(tabKey: string) {
    const tab = meta.tabs.find((t) => t.key === tabKey)
    if (!tab) return
    const analysis = tab.analyses.includes(state.analysis)
      ? state.analysis
      : tab.analyses[0]
    onChange({
      tab: tabKey,
      analysis,
      params: defaultParams(meta, analysis, state.params),
    })
  }

  function pickAnalysis(analysis: string) {
    onChange({
      analysis,
      tab: tabOfAnalysis(meta, analysis),
      params: defaultParams(meta, analysis),
    })
  }

  const spec = meta.analyses.find((a) => a.name === state.analysis)

  function label(name: string): string {
    return meta.analyses.find((a) => a.name === name)?.label ?? name
  }

  return (
    <aside className="w-56 shrink-0 space-y-4 border-r p-3">
      <div className="space-y-1">
        {meta.tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => pickTab(t.key)}
            className={`w-full rounded-md px-2.5 py-1.5 text-left text-sm ${
              t.key === state.tab
                ? "bg-primary text-primary-foreground"
                : "hover:bg-accent"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="space-y-1.5">
        <div className="px-1 text-xs font-medium text-muted-foreground">분석</div>
        <div className="flex flex-wrap gap-1.5">
          {currentTab?.analyses.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => pickAnalysis(name)}
              className={`rounded-full border px-2.5 py-1 text-xs ${
                name === state.analysis
                  ? "border-primary bg-primary/10 font-medium text-primary"
                  : "hover:bg-accent"
              }`}
            >
              {label(name)}
            </button>
          ))}
        </div>
      </div>

      {spec && spec.params.length > 0 && (
        <div className="space-y-2">
          <div className="px-1 text-xs font-medium text-muted-foreground">
            파라미터
          </div>
          {spec.params.map((p) => {
            // kind="screen" 은 choices 가 없다 — present_screens(전이 큐브 화면 목록)로 채운다.
            const options = p.kind === "screen" ? meta.present_screens : p.choices
            return (
              <label key={p.name} className="block space-y-1">
                <span className="px-1 text-xs text-muted-foreground">
                  {p.name}
                  {p.required && <span className="text-red-500"> *</span>}
                </span>
                <select
                  value={state.params[p.name] ?? ""}
                  onChange={(e) =>
                    onChange({ params: { ...state.params, [p.name]: e.target.value } })
                  }
                  className="w-full rounded-md border px-2 py-1 text-sm"
                >
                  {options.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            )
          })}
        </div>
      )}
    </aside>
  )
}

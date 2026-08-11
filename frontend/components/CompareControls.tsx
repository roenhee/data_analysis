"use client"

import type { Meta } from "@/lib/api"
import type { DashState } from "@/lib/state"

/** 비교 모드 컨트롤: 어느 세그먼트 축의 두 값(A vs B)을 견줄지. 축을 바꾸면 A·B 를 그 축의
 *  첫 두 값으로 리셋한다(A·B 는 달라야 뜻이 있다). */
export function CompareControls({
  meta,
  state,
  onChange,
}: {
  meta: Meta
  state: DashState
  onChange: (patch: Partial<DashState>) => void
}) {
  const axis = meta.segments.find((s) => s.axis === state.cmpOn)
  const values = axis?.values ?? []

  function pickAxis(on: string) {
    const vals = meta.segments.find((s) => s.axis === on)?.values ?? []
    onChange({ cmpOn: on, cmpA: vals[0] ?? "", cmpB: vals[1] ?? vals[0] ?? "" })
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-blue-50/40 px-6 py-2.5">
      <span className="text-sm font-medium">비교</span>
      <select
        value={state.cmpOn}
        onChange={(e) => pickAxis(e.target.value)}
        className="rounded-md border px-2 py-1 text-sm"
      >
        {meta.segments.map((s) => (
          <option key={s.axis} value={s.axis}>
            {s.label}
          </option>
        ))}
      </select>
      <select
        value={state.cmpA}
        onChange={(e) => onChange({ cmpA: e.target.value })}
        className="rounded-md border px-2 py-1 text-sm"
      >
        {values.map((v) => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>
      <span className="text-muted-foreground">vs</span>
      <select
        value={state.cmpB}
        onChange={(e) => onChange({ cmpB: e.target.value })}
        className="rounded-md border px-2 py-1 text-sm"
      >
        {values.map((v) => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>
      <span className="text-xs text-muted-foreground">
        (지표는 A − B · 날짜별 델타를 함께 봅니다)
      </span>
    </div>
  )
}

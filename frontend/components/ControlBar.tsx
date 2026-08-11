"use client"

import type { Meta } from "@/lib/api"
import {
  type DashState,
  HARD_LIMIT_DAYS,
  SOFT_LIMIT_DAYS,
  periodDays,
} from "@/lib/state"
import { MultiSelect } from "@/components/MultiSelect"

/** 상단 컨트롤바: 기간(빌드된 범위로 경계) + 세그먼트 축 6개(다중선택).
 *  서비스 scope 는 여기 없다 — 빌드 범위라 고정이다(스펙). */
export function ControlBar({
  meta,
  state,
  onChange,
}: {
  meta: Meta
  state: DashState
  onChange: (patch: Partial<DashState>) => void
}) {
  const first = meta.present_dates[0]
  const last = meta.present_dates[meta.present_dates.length - 1]
  const days = periodDays(state.start, state.end)
  const overHard = days > HARD_LIMIT_DAYS
  const overSoft = days > SOFT_LIMIT_DAYS

  function setSegment(axis: string, next: string[]) {
    const segments = { ...state.segments }
    if (next.length) segments[axis] = next
    else delete segments[axis]
    onChange({ segments })
  }

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b bg-muted/30 px-6 py-2.5">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">기간</span>
        <input
          type="date"
          value={state.start}
          min={first}
          max={state.end}
          onChange={(e) => onChange({ start: e.target.value })}
          className="rounded-md border px-2 py-1 text-sm"
        />
        <span className="text-muted-foreground">–</span>
        <input
          type="date"
          value={state.end}
          min={state.start}
          max={last}
          onChange={(e) => onChange({ end: e.target.value })}
          className="rounded-md border px-2 py-1 text-sm"
        />
        <span className="text-xs text-muted-foreground">{days}일</span>
        {overHard ? (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
            {HARD_LIMIT_DAYS}일 초과 — 좁혀주세요
          </span>
        ) : overSoft ? (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
            한 달 초과 — 느려질 수 있음
          </span>
        ) : null}
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-2">
        {meta.segments.map((s) => (
          <MultiSelect
            key={s.axis}
            label={s.label}
            options={s.values}
            selected={state.segments[s.axis] ?? []}
            onChange={(next) => setSegment(s.axis, next)}
          />
        ))}
      </div>
    </div>
  )
}

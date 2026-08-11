"use client"

import { useEffect, useRef, useState } from "react"
import { ChevronDown } from "lucide-react"

/** 체크박스 드롭다운 다중선택. 세그먼트 축(값이 여럿, 선택 안 하면 "전체")에 쓴다.
 *  네이티브 <select multiple> 은 ctrl-click 이 필요해 쓰기 나쁘다 — 버튼+팝오버로 대체. */
export function MultiSelect({
  label,
  options,
  selected,
  onChange,
}: {
  label: string
  options: string[]
  selected: string[]
  onChange: (next: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDown)
    return () => document.removeEventListener("mousedown", onDown)
  }, [open])

  function toggle(value: string) {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    )
  }

  const summary = selected.length === 0 ? "전체" : `${selected.length}개`

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm hover:bg-accent"
        title={selected.length ? selected.join(", ") : "전체"}
      >
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{summary}</span>
        <ChevronDown className="h-3.5 w-3.5 opacity-60" />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 max-h-64 min-w-40 overflow-auto rounded-md border bg-background p-1 shadow-md">
          {selected.length > 0 && (
            <button
              type="button"
              onClick={() => onChange([])}
              className="mb-1 w-full rounded px-2 py-1 text-left text-xs text-muted-foreground hover:bg-accent"
            >
              선택 해제(전체 보기)
            </button>
          )}
          {options.map((opt) => (
            <label
              key={opt}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-accent"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={() => toggle(opt)}
              />
              <span>{opt}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

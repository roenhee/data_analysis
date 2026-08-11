"use client"

import type { Envelope as EnvelopeType } from "@/lib/api"

/** 봉투: 분석이 붙인 경고(기간 과대·other 뭉침 등)와 조회 범위 요약.
 *  "그럴듯한데 틀린 숫자"를 막는 맥락이라 결과 위에 눈에 띄게 둔다. */
export function Envelope({ envelope }: { envelope: EnvelopeType }) {
  const warnings = envelope.warnings ?? []
  return (
    <div className="space-y-2">
      {warnings.length > 0 && (
        <ul className="space-y-1">
          {warnings.map((w, i) => (
            <li
              key={i}
              className="rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm text-amber-800"
            >
              {w}
            </li>
          ))}
        </ul>
      )}
      <div className="text-xs text-muted-foreground">
        빌드일 {envelope.n_dates}일
        {envelope.period_days != null && ` · 조회 ${envelope.period_days}일`}
        {" · "}
        사전 {envelope.state_dict_version}
      </div>
    </div>
  )
}

"use client"

import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import type { Column } from "@/lib/api"
import { PAGE_SIZE } from "@/lib/state"

/** 서버 페이지네이션. `rows` 는 **이미 이 페이지의 행**(서버가 슬라이스), `total` 은 전체
 *  행수다. 페이지 이동은 상위(dash.page)로 올라가 서버 재조회를 부른다 — 큰 프레임을 전량
 *  전송하지 않는다(분석 결과는 서버가 캐시해 재계산 없이 다음 페이지를 낸다). */
export function ResultTable({
  columns,
  rows,
  total,
  page,
  onPageChange,
}: {
  columns: Column[]
  rows: unknown[][]
  total: number
  page: number
  onPageChange: (page: number) => void
}) {
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const current = Math.min(Math.max(1, page), pageCount)
  const startIdx = (current - 1) * PAGE_SIZE

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((c) => (
                <TableHead key={c.key} title={c.help ?? undefined}>{c.label}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, i) => (
              <TableRow key={startIdx + i}>
                {row.map((cell, j) => (
                  <TableCell key={j}>{cell == null ? "" : String(cell)}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {startIdx + 1}–{Math.min(startIdx + rows.length, total)} / 총{" "}
            {total.toLocaleString()}행
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={current <= 1}
              onClick={() => onPageChange(current - 1)}
            >
              이전
            </Button>
            <span>
              {current} / {pageCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={current >= pageCount}
              onClick={() => onPageChange(current + 1)}
            >
              다음
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

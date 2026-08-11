"use client"

import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import type { Column } from "@/lib/api"

const PAGE_SIZE = 25

/** 클라이언트 페이지네이션. 전체 rows 를 받아 page 슬라이스만 그린다(서버 페이지네이션은
 *  범위 밖). page 는 상위(dash.page)에서 와 URL 공유된다. */
export function ResultTable({
  columns,
  rows,
  page,
  onPageChange,
}: {
  columns: Column[]
  rows: unknown[][]
  page: number
  onPageChange: (page: number) => void
}) {
  const total = rows.length
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const current = Math.min(Math.max(1, page), pageCount)
  const startIdx = (current - 1) * PAGE_SIZE
  const slice = rows.slice(startIdx, startIdx + PAGE_SIZE)

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
            {slice.map((row, i) => (
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
            {startIdx + 1}–{Math.min(startIdx + PAGE_SIZE, total)} / 총{" "}
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

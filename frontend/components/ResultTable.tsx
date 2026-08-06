import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table"
import type { Column } from "@/lib/api"

/** 골격은 앞 50행만. 페이지네이션은 2단계. */
export function ResultTable({ columns, rows }: { columns: Column[]; rows: unknown[][] }) {
  const page = rows.slice(0, 50)
  return (
    <div className="rounded-md border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((c) => (
              <TableHead key={c.key} title={c.help ?? undefined}>{c.label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.map((row, i) => (
            <TableRow key={i}>
              {row.map((cell, j) => (
                <TableCell key={j}>{cell == null ? "" : String(cell)}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

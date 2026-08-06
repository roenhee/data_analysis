import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import type { Headline } from "@/lib/api"

export function ResultCards({ headline }: { headline: Headline[] }) {
  if (!headline.length) return null
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {headline.map((h) => (
        <Card key={h.label}>
          <CardHeader className="pb-1">
            <CardTitle
              className="text-sm font-normal text-muted-foreground"
              title={h.help ?? undefined}
            >
              {h.label}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{h.value}</CardContent>
        </Card>
      ))}
    </div>
  )
}

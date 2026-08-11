import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

/** 전체폭 최상단 헤더: Markov 로고 + 단일/비교 모드 탭. */
export function Header({
  mode = "single",
  onModeChange,
}: {
  mode?: "single" | "compare"
  onModeChange?: (mode: "single" | "compare") => void
}) {
  return (
    <header className="w-full border-b px-6 py-3 flex items-center gap-6">
      <div
        className="text-2xl font-bold tracking-tight leading-none"
        style={{ fontFamily: "Georgia, 'Times New Roman', serif", color: "#4e79a7" }}
      >
        Markov<span style={{ color: "#f28e2b" }}>.</span>
      </div>
      <Tabs
        value={mode}
        onValueChange={(v) => onModeChange?.(v as "single" | "compare")}
      >
        <TabsList>
          <TabsTrigger value="single">단일</TabsTrigger>
          <TabsTrigger value="compare">비교</TabsTrigger>
        </TabsList>
      </Tabs>
    </header>
  )
}

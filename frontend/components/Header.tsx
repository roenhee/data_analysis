import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

/** 전체폭 최상단 헤더: Markov 로고 + 단일/비교 모드 탭(비교는 3단계라 비활성). */
export function Header() {
  return (
    <header className="w-full border-b px-6 py-3 flex items-center gap-6">
      <div
        className="text-2xl font-bold tracking-tight leading-none"
        style={{ fontFamily: "Georgia, 'Times New Roman', serif", color: "#4e79a7" }}
      >
        Markov<span style={{ color: "#f28e2b" }}>.</span>
      </div>
      <Tabs value="single">
        <TabsList>
          <TabsTrigger value="single">단일</TabsTrigger>
          <TabsTrigger value="compare" disabled title="비교 모드는 다음 단계에서 열립니다">
            비교
          </TabsTrigger>
        </TabsList>
      </Tabs>
    </header>
  )
}

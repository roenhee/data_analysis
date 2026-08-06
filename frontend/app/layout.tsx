import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "Markov 대시보드",
  description: "정량 분석 대시보드",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-full flex flex-col antialiased">{children}</body>
    </html>
  )
}

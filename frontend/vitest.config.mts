import path from "node:path"
import { defineConfig } from "vitest/config"

// 순수 로직(lib/state·api)만 단위 테스트한다 — DOM 불필요라 node 환경. @ alias 는 tsconfig 와 짝.
export default defineConfig({
  test: { environment: "node", include: ["lib/**/*.test.ts"] },
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
})

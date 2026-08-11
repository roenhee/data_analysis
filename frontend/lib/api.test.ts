import { describe, expect, it } from "vitest"
import { buildQuery } from "@/lib/api"

describe("buildQuery", () => {
  it("repeats array values and sets scalars (백엔드 계약: 세그먼트 반복, 파라미터 set)", () => {
    const qs = buildQuery({ os: ["android", "ios"], start: "2026-07-14", n: "3" })
    expect(qs.getAll("os")).toEqual(["android", "ios"])
    expect(qs.get("start")).toBe("2026-07-14")
    expect(qs.get("n")).toBe("3")
  })

  it("produces a stable query string", () => {
    const qs = buildQuery({ start: "2026-07-14", end: "2026-07-16" })
    expect(qs.toString()).toBe("start=2026-07-14&end=2026-07-16")
  })
})

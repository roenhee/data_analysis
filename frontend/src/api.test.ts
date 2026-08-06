import { describe, it, expect } from "vitest"
import { buildQuery } from "@/api"

describe("buildQuery", () => {
  it("sets scalar params and repeats array params", () => {
    const qs = buildQuery({ start: "2026-07-14", end: "2026-07-28", os: ["android", "ios"] })
    expect(qs.get("start")).toBe("2026-07-14")
    expect(qs.getAll("os")).toEqual(["android", "ios"])
  })
})

import { describe, expect, it } from "vitest"
import type { Meta } from "@/lib/api"
import {
  defaultParams,
  initialState,
  periodDays,
  toQuery,
} from "@/lib/state"

const meta: Meta = {
  tabs: [
    { key: "overview", label: "개요", analyses: ["session_trend"] },
    { key: "flow", label: "화면흐름", analyses: ["screen_flow", "reachability"] },
  ],
  analyses: [
    { name: "session_trend", label: "세션 추이", help: null, params: [] },
    {
      name: "screen_flow",
      label: "화면 흐름",
      help: null,
      params: [
        { name: "exit_within", label: "이탈 구간", help: null, kind: "pair", required: false, choices: ["", "1,3"] },
        { name: "damping", label: "감쇠 계수", help: null, kind: "float", required: false, choices: ["0.85", "0.8"] },
      ],
    },
    {
      name: "reachability",
      label: "도달 확률",
      help: null,
      params: [
        { name: "source", label: "출발 화면", help: null, kind: "screen", required: true, choices: [] },
        { name: "target", label: "도착 화면", help: null, kind: "screen", required: true, choices: [] },
        { name: "max_k", label: "최대 걸음 수", help: null, kind: "int", required: false, choices: ["10", "6"] },
      ],
    },
  ],
  segments: [
    { axis: "os", label: "운영체제", values: ["android", "ios"] },
    { axis: "gender", label: "성별", values: ["F", "M"] },
  ],
  present_dates: ["2026-07-14", "2026-08-04"],
  present_services: ["top"],
  present_screens: ["a/x", "b/y", "c/z"],
  defaults: { analysis: "session_trend", state_dict_version: "sd" },
}

describe("initialState", () => {
  it("defaults to the overview analysis over the built range", () => {
    const s = initialState(meta, "")
    expect(s.tab).toBe("overview")
    expect(s.analysis).toBe("session_trend")
    expect(s.end).toBe("2026-08-04")
    expect(s.start).toBe("2026-07-14") // 한 달 전이 첫날보다 이르면 첫날로 클램프
    expect(s.segments).toEqual({})
    expect(s.params).toEqual({})
    expect(s.page).toBe(1)
  })

  it("reads tab, analysis, period, repeated segments, params, page from the URL", () => {
    const s = initialState(
      meta,
      "?tab=flow&analysis=screen_flow&start=2026-07-20&end=2026-07-25&os=android&os=ios&damping=0.8&page=3",
    )
    expect(s.tab).toBe("flow")
    expect(s.analysis).toBe("screen_flow")
    expect(s.start).toBe("2026-07-20")
    expect(s.end).toBe("2026-07-25")
    expect(s.segments).toEqual({ os: ["android", "ios"] })
    // URL 에 없는 파라미터는 기본값으로 채운다.
    expect(s.params).toEqual({ exit_within: "", damping: "0.8" })
    expect(s.page).toBe(3)
  })
})

describe("toQuery round-trip", () => {
  it("reproduces the state through URL encode/decode", () => {
    const s1 = initialState(
      meta,
      "?tab=flow&analysis=reachability&start=2026-07-20&end=2026-07-25&source=a/x&target=b/y&max_k=6&os=android",
    )
    const s2 = initialState(meta, `?${toQuery(s1)}`)
    expect(s2).toEqual(s1)
  })
})

describe("defaultParams", () => {
  it("fills screen params from present_screens, distinctly", () => {
    expect(defaultParams(meta, "reachability")).toEqual({
      source: "a/x",
      target: "b/y",
      max_k: "10",
    })
  })

  it("fills choice params with the first choice", () => {
    expect(defaultParams(meta, "screen_flow")).toEqual({
      exit_within: "",
      damping: "0.85",
    })
  })
})

describe("periodDays", () => {
  it("counts inclusive of both ends", () => {
    expect(periodDays("2026-07-14", "2026-07-14")).toBe(1)
    expect(periodDays("2026-07-14", "2026-08-04")).toBe(22)
  })
})

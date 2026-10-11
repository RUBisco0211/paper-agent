import { describe, expect, it } from "vitest"

import { normalizePdfQuoteRects, messageReferenceFromSelection, readQuoteReferences } from "./quote-references"

describe("quoted references", () => {
  it("keeps the rendered selection locator and comment in user message metadata", () => {
    const ref = messageReferenceFromSelection("reply", 0, 2, 10, "verified", "Why?")
    expect(ref.start).toBe(2)
    expect(ref.end).toBe(10)
    expect(readQuoteReferences({ paper_agent: { references: [ref] } })).toEqual([ref])
  })

  it("preserves every valid rectangle in a multi-line PDF selection", () => {
    const rects = Array.from({ length: 30 }, (_, index) => [0.1, index / 40, 0.4, index / 40 + 0.01])
    const compacted = normalizePdfQuoteRects(rects)
    expect(compacted).toHaveLength(30)
    expect(compacted[0][1]).toBe(0)
    expect(compacted.at(-1)?.[3]).toBeCloseTo(29 / 40 + 0.01)
  })

  it("keeps distinct text fragments on one PDF line", () => {
    expect(normalizePdfQuoteRects([[0.1, 0.2, 0.2, 0.22], [0.21, 0.2, 0.3, 0.22]])).toEqual([[0.1, 0.2, 0.2, 0.22], [0.21, 0.2, 0.3, 0.22]])
  })
})

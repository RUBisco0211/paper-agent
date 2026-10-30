import { describe, expect, it } from "vitest"
import type { Msg } from "@agentscope-ai/agentscope/message"

import { registeredCitations, renderCitationTags } from "@/lib/citations"

const first = "cit_0123456789ab"
const second = "cit_fedcba987654"

function messageWith(content: unknown[]): Msg {
  return { id: "m-1", role: "assistant", content } as unknown as Msg
}

describe("registered citations", () => {
  it("collects the ids the session's searches returned", () => {
    const messages = [
      messageWith([
        { type: "tool_result", id: "call-1", name: "search_papers", state: "success",
          output: JSON.stringify({ status: "ok", evidence: [{ citation_id: first, snippet: "片段" }] }) },
        { type: "tool_result", id: "call-2", name: "web_search", state: "success",
          output: JSON.stringify({ results: [{ citation_id: second }] }) },
      ]),
      messageWith([
        { type: "tool_result", id: "call-3", name: "search_papers", state: "success",
          output: [{ type: "text", text: JSON.stringify({ evidence: [{ citation_id: second }] }) }] },
      ]),
    ]

    expect([...registeredCitations(messages)]).toEqual([first, second])
  })

  it("ignores ids in the wrong format and results that are not JSON", () => {
    const messages = [
      messageWith([
        { type: "tool_result", id: "call-1", name: "search_papers", state: "success",
          output: JSON.stringify({ evidence: [{ citation_id: "cid_0123456789ab" }, { citation_id: "cit_short" }] }) },
        { type: "tool_result", id: "call-2", name: "search_papers", state: "success", output: "not json" },
      ]),
    ]

    expect(registeredCitations(messages).size).toBe(0)
  })
})

describe("citation markers", () => {
  it("numbers the registered markers in reading order", () => {
    const order = new Map<string, number>()
    expect(
      renderCitationTags(`先说结论 [${first}]，再补一句 [${second}]。`, new Set([first, second]), order),
    ).toBe(
      `先说结论 <paper-citation data-cid="${first}">[1]</paper-citation>，再补一句 <paper-citation data-cid="${second}">[2]</paper-citation>。`,
    )
  })

  it("reuses the number when the same evidence is cited twice", () => {
    const order = new Map<string, number>()
    renderCitationTags(`a [${first}]`, new Set([first]), order)
    expect(renderCitationTags(`b [${first}]`, new Set([first]), order)).toBe(
      `b <paper-citation data-cid="${first}">[1]</paper-citation>`,
    )
  })

  it("leaves a marker the session never registered as plain text", () => {
    const order = new Map<string, number>()
    expect(renderCitationTags(`结论 [${first}]`, new Set(), order)).toBe(`结论 [${first}]`)
  })

  it("keeps literals inside code fences and inline code untouched", () => {
    const order = new Map<string, number>()
    const known = new Set([first])
    expect(renderCitationTags(`\`\`\`\n[${first}]\n\`\`\``, known, order)).toBe(`\`\`\`\n[${first}]\n\`\`\``)
    expect(renderCitationTags(`\`[${first}]\``, known, order)).toBe(`\`[${first}]\``)
    expect(order.size).toBe(0)
  })
})

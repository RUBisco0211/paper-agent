// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { SessionEntry } from "@/lib/api"

import { EntryList } from "./entry-list"

function entry(payload: Record<string, unknown>, sequence = 1): SessionEntry {
  return {
    id: `entry-${sequence}`,
    sequence,
    parent_id: null,
    type: "message",
    timestamp: "2026-09-17T00:00:00Z",
    schema_version: 1,
    payload,
  }
}

describe("EntryList", () => {
  it("marks a stopped answer as aborted without claiming success", () => {
    render(
      <EntryList
        entries={[
          entry({ role: "assistant", content: "部分回答", stop_reason: "aborted" }),
        ]}
        streamingText=""
        generating={false}
        onCitationClick={() => {}}
      />,
    )

    expect(screen.getByText("部分回答")).toBeTruthy()
    expect(screen.getByText(/已停止/)).toBeTruthy()
  })

  it("explains a failed generation with a stable code and keeps it visible", () => {
    render(
      <EntryList
        entries={[
          entry({
            role: "assistant",
            content: "",
            stop_reason: "failed",
            error_code: "search_unavailable",
          }),
        ]}
        streamingText=""
        generating={false}
        onCitationClick={() => {}}
      />,
    )

    expect(screen.getByText(/检索服务暂时不可用/)).toBeTruthy()
  })

  it("renders citations as resolvable buttons", async () => {
    const onCitationClick = vi.fn()
    render(
      <EntryList
        entries={[
          entry({
            role: "assistant",
            content: "见证据",
            stop_reason: "completed",
            citations: ["cit_abc123"],
          }),
        ]}
        streamingText=""
        generating={false}
        onCitationClick={onCitationClick}
      />,
    )

    screen.getByRole("button", { name: /cit_abc123/ }).click()
    expect(onCitationClick).toHaveBeenCalledWith("cit_abc123")
  })

  it("shows the streaming placeholder while generating", () => {
    render(
      <EntryList
        entries={[]}
        streamingText="正在写"
        generating
        onCitationClick={() => {}}
      />,
    )

    expect(screen.getByText(/正在写/)).toBeTruthy()
  })
})

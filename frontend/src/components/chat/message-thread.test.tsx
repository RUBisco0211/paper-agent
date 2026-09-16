// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { SessionEntry } from "@/lib/api"

import { MessageThread } from "./message-thread"

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

function renderThread(entries: SessionEntry[], generating = false, streamingText = "") {
  return render(
    <MessageThread
      entries={entries}
      streamingText={streamingText}
      generating={generating}
      onCitationClick={() => {}}
    />,
  )
}

describe("MessageThread", () => {
  it("marks a stopped answer as stopped without claiming success", () => {
    renderThread([
      entry({ role: "assistant", content: "部分回答", stop_reason: "aborted" }),
    ])

    expect(screen.getByText("部分回答")).toBeTruthy()
    expect(screen.getByText("已停止")).toBeTruthy()
  })

  it("explains a failed generation in user terms", () => {
    renderThread([
      entry({
        role: "assistant",
        content: "",
        stop_reason: "failed",
        error_code: "search_unavailable",
      }),
    ])

    expect(screen.getByText(/检索暂时不可用/)).toBeTruthy()
    // 内部错误码不出现在界面上
    expect(screen.queryByText(/search_unavailable/)).toBeNull()
  })

  it("renders citations as clickable references", async () => {
    const onCitationClick = vi.fn()
    render(
      <MessageThread
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

  it("shows the streaming text while generating", () => {
    renderThread([], true, "正在写")

    expect(screen.getByText("正在写")).toBeTruthy()
  })
})

// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
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

function renderThread(
  entries: SessionEntry[],
  generating = false,
  streamingText = "",
  streamingThinking = "",
) {
  return render(
    <MessageThread
      entries={entries}
      streamingText={streamingText}
      streamingThinking={streamingThinking}
      generating={generating}
      onCitationClick={() => {}}
    />,
  )
}

describe("MessageThread", () => {
  it("marks a stopped answer as stopped without claiming success", () => {
    const { container } = renderThread([
      entry({ role: "assistant", content: "部分回答", stop_reason: "aborted" }),
    ])

    expect(screen.getByText("部分回答")).toBeTruthy()
    expect(screen.getByText("已停止")).toBeTruthy()
    expect(container.querySelector('[data-slot="message-avatar"]')).toBeNull()
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

    screen.getByRole("button", { name: /引用 1/ }).click()
    expect(onCitationClick).toHaveBeenCalledWith("cit_abc123")
  })

  it("renders registered citation markers as numbered inline links", () => {
    const onCitationClick = vi.fn()
    render(
      <MessageThread
        entries={[
          entry({
            role: "assistant",
            content: "结论由实验支持 [cit_abc123]，未知标记保持原文 [cit_unknown]。",
            citations: ["cit_abc123"],
          }),
        ]}
        streamingText=""
        generating={false}
        onCitationClick={onCitationClick}
      />,
    )

    const citation = screen.getByRole("link", { name: "打开引用 1" })
    expect(citation.hasAttribute("data-paper-citation")).toBe(true)
    expect(citation.className).toContain("bg-primary/10")
    citation.click()
    expect(onCitationClick).toHaveBeenCalledWith("cit_abc123")
    expect(screen.getByText("[cit_unknown]", { exact: false })).toBeTruthy()
    expect(screen.queryByRole("button", { name: "引用 1" })).toBeNull()
  })

  it("separates live tool activity from streaming answer text", () => {
    render(
      <MessageThread
        entries={[]}
        streamingText="正在写"
        generating
        activeTools={[{ id: "tool-1", name: "search_papers" }]}
        onCitationClick={() => {}}
      />,
    )

    expect(screen.getByText("正在写")).toBeTruthy()
    expect(screen.getByText("检索文献")).toBeTruthy()
    expect(screen.getByText("正在生成…")).toBeTruthy()
    expect(
      screen.getByText("正在写").closest('[data-slot="bubble"]')?.getAttribute("data-variant"),
    ).toBe("ghost")
  })

  it("renders assistant Markdown structure and math", () => {
    renderThread([
      entry({
        role: "assistant",
        content: [
          "## 结论",
          "",
          "- **准确率**提高",
          "- 支持表格",
          "",
          "| 方法 | 分数 |",
          "| --- | ---: |",
          "| A | 92 |",
          "",
          "行内公式 $\\tilde{B}$、$E = mc^2$ 与 \\(a^2+b^2=c^2\\)。",
          "",
          "$$V^{h,\\mu}(x) = \\max\\{h(x),\\; V^{h,\\mu}(f(x, \\mu(x)))\\} \\tag{21}$$",
          "",
          "\\[",
          "\\sum_{i=1}^{n} i",
          "\\]",
          "",
          "`\\(代码示例\\)`",
        ].join("\n"),
      }),
    ])

    expect(screen.getByRole("heading", { name: "结论", level: 2 })).toBeTruthy()
    expect(screen.getByText("准确率").getAttribute("data-streamdown")).toBe("strong")
    expect(screen.getByRole("table")).toBeTruthy()
    expect(document.querySelectorAll("mjx-container")).toHaveLength(5)
    expect(document.querySelectorAll(".agent-markdown")).toHaveLength(1)
    expect(document.querySelectorAll('mjx-container[display="true"]')).toHaveLength(2)
    expect(
      [...document.querySelectorAll("mjx-container")].every((formula) =>
        formula.querySelector("svg"),
      ),
    ).toBe(true)
    expect(screen.getByText("\\(代码示例\\)")).toBeTruthy()
    expect(document.querySelector('p mjx-container[display="true"]')).toBeNull()
  })

  it("keeps incomplete Markdown formatted while text is streaming", () => {
    renderThread([], true, "**正在生成")

    expect(screen.getByText("正在生成").getAttribute("data-streamdown")).toBe("strong")
  })

  it("keeps MathJax formulas intact when a streamed answer is persisted", () => {
    const formula =
      "$$\\tilde{V}^{h^{(m)},\\mu}(o_i^0) = V_i^{h^{(m)},\\mu}(\\mathbf{x}^0) := \\max_{k \\geq 0} h^{(m)}(o_i^k)$$"
    const view = renderThread([], true, formula)

    expect(document.querySelector("mjx-container svg")).toBeTruthy()

    view.rerender(
      <MessageThread
        entries={[entry({ role: "assistant", content: formula })]}
        streamingText=""
        generating={false}
        onCitationClick={() => {}}
      />,
    )

    expect(document.querySelector('mjx-container[display="true"] svg')).toBeTruthy()
  })

  it("renders persisted thinking as a collapsible block", async () => {
    const user = userEvent.setup()
    renderThread([
      entry({
        role: "assistant",
        thinking: "先检索相关实验，再核对表格。",
        content: "最终回答",
      }),
    ])

    expect(screen.queryByText("先检索相关实验，再核对表格。")).toBeNull()
    await user.click(screen.getByRole("button", { name: /思考过程/ }))
    expect(screen.getByText("先检索相关实验，再核对表格。")).toBeTruthy()
  })

  it("does not infer thinking from assistant prose", () => {
    renderThread([
      entry({
        role: "assistant",
        content: "I'll start with the background.\n\n# 正文",
      }),
    ])

    expect(screen.getByText("I'll start with the background.")).toBeTruthy()
    expect(screen.getByRole("heading", { name: "正文" })).toBeTruthy()
    expect(screen.queryByRole("button", { name: /思考过程/ })).toBeNull()
  })

  it("groups intermediate messages and tools into a collapsed timed trace", async () => {
    const user = userEvent.setup()
    const question = entry({ role: "user", content: "总结文献" }, 1)
    const traceMessage = entry(
      { role: "assistant", content: "先检索相关章节。", trace: true },
      2,
    )
    const first = {
      ...entry(
        {
          tool: "search_papers",
          state: "success",
          content: '{"scope":"project","count":1}',
        },
        3,
      ),
      type: "tool_result" as const,
    }
    const second = {
      ...entry({ tool: "get_paper_excerpt", state: "success", content: "second" }, 4),
      type: "tool_result" as const,
    }
    const answer = entry({ role: "assistant", content: "最终回答" }, 5)

    renderThread([question, traceMessage, first, second, answer])

    const traceToggle = screen.getByRole("button", { name: /用时 1 秒/ })
    expect(screen.queryByText("先检索相关章节。")).toBeNull()
    expect(screen.getByText("最终回答")).toBeTruthy()
    await user.click(traceToggle)
    expect(screen.getByText("先检索相关章节。")).toBeTruthy()
    expect(screen.getByText("检索文献")).toBeTruthy()
    expect(screen.queryByText("已完成")).toBeNull()
    const firstTool = screen.getByRole("button", { name: "检索文献" })
    expect(screen.queryByText('"scope": "project"', { exact: false })).toBeNull()
    await user.click(firstTool)
    const json = document.querySelector('[data-language="json"]')
    expect(json).toBeTruthy()
    expect(json?.textContent).toContain('"scope": "project"')
    expect(json?.textContent).toContain('"count": 1')
    await user.click(firstTool)
    expect(document.querySelector('[data-language="json"]')).toBeNull()
  })

  it("formats a legacy tool result truncated inside a JSON string", async () => {
    const user = userEvent.setup()
    const tool = {
      ...entry(
        {
          tool: "search_papers",
          state: "success",
          content: '{"scope":"project","evidence":[{"snippet":"unfinished',
        },
        2,
      ),
      type: "tool_result" as const,
    }

    renderThread([tool])
    await user.click(screen.getByRole("button", { name: "检索文献" }))

    const json = document.querySelector('[data-language="json"]')
    expect(json).toBeTruthy()
    expect(json?.textContent).toContain('"scope": "project"')
    expect(json?.textContent).toContain('  "scope": "project"')
    expect(json?.textContent).toContain('    {      "snippet": "unfinished')
  })
})

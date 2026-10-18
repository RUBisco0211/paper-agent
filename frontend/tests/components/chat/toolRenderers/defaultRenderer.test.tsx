// @vitest-environment jsdom
import { render } from "@testing-library/react"
import { expect, it } from "vitest"

import { defaultRenderBody } from "@/components/chat/toolRenderers/defaultRenderer"
import type { ToolCallWithResult } from "@/components/chat/toolRenderers/types"

const t = (key: string) => key

function pair(output: string): ToolCallWithResult {
  return {
    call: {
      id: "call-1",
      type: "tool_call",
      name: "get_paper_excerpt",
      input: "{}",
      state: "success",
    },
    result: {
      id: "call-1",
      type: "tool_result",
      name: "get_paper_excerpt",
      output,
      state: "success",
    },
  } as unknown as ToolCallWithResult
}

it("pretty-prints a JSON tool result with indentation", () => {
  const view = render(
    <>{defaultRenderBody(pair('{"items":[{"title":"A"}],"total":1}'), t)}</>,
  )

  expect(view.container.querySelector("pre")?.textContent).toBe(
    JSON.stringify({ items: [{ title: "A" }], total: 1 }, null, 2),
  )
})

it("keeps plain tool output unchanged", () => {
  const view = render(<>{defaultRenderBody(pair("已加入入库队列"), t)}</>)

  expect(view.container.querySelector("pre")?.textContent).toBe("已加入入库队列")
})

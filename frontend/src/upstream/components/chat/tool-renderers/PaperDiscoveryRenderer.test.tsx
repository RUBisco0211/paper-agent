// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"

import { DiscoveryImportContext, PaperDiscoveryRenderer } from "./PaperDiscoveryRenderer"
import type { ToolCallWithResult } from "./types"

it("submits only checked discovery candidates when the user confirms", async () => {
  const approve = vi.fn(async () => undefined)
  const pair = {
    call: { id: "call-1", name: "discover_papers" },
    result: { state: "success", output: JSON.stringify({ papers: [
      { source_id: "https://openalex.org/W1", title: "Selected paper", candidate_token: "signed-1" },
      { source_id: "https://openalex.org/W2", title: "Other paper", candidate_token: "signed-2" },
    ] }) },
  } as ToolCallWithResult
  render(<DiscoveryImportContext.Provider value={approve}>
    {PaperDiscoveryRenderer.renderBody!(pair, (key) => key)}
  </DiscoveryImportContext.Provider>)
  fireEvent.click(screen.getByLabelText(/Selected paper/))
  fireEvent.click(screen.getByRole("button", { name: "选择入库（1）" }))
  fireEvent.click(screen.getByRole("button", { name: "确认导入" }))
  await waitFor(() => expect(approve).toHaveBeenCalledWith(["signed-1"]))
})

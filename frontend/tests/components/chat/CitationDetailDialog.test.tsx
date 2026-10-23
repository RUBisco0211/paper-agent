// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { CitationDetailDialog, type CitationBlock } from "@/components/chat/CitationDetailDialog"

const blocks: CitationBlock[] = [
  { block_id: 17, page: 3 },
  { block_id: 18, page: 3 },
  { block_id: 21, page: 4 },
]

function open(overrides: Partial<Parameters<typeof CitationDetailDialog>[0]> = {}) {
  const onOpenBlock = vi.fn()
  const onOpenChange = vi.fn()
  render(
    <CitationDetailDialog
      open
      blocks={blocks}
      snippet="The attention mechanism maps a query."
      onOpenChange={onOpenChange}
      onOpenBlock={onOpenBlock}
      {...overrides}
    />,
  )
  return { onOpenBlock, onOpenChange }
}

describe("CitationDetailDialog", () => {
  it("lists every block of the citation when the evidence spans several pages", () => {
    open()

    expect(screen.getByText("证据包含 3 个段落，分布在 2 页")).toBeTruthy()
    expect(screen.getAllByRole("button", { name: /定位/ })).toHaveLength(3)
  })

  it("opens the paper at the chosen block when a list item is clicked", () => {
    const { onOpenBlock } = open()

    fireEvent.click(screen.getAllByRole("button", { name: /定位/ })[2])

    expect(onOpenBlock).toHaveBeenCalledWith(21, 4)
  })

  it("does not expose internal block identifiers in the list", () => {
    open()

    expect(screen.queryByText(/17/)).toBeNull()
    expect(screen.queryByText(/block_id/)).toBeNull()
  })
})

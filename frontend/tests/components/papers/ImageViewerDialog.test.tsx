// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ImageViewerDialog } from "@/components/papers/ImageViewerDialog"

const source = "data:image/png;base64,iVBORw0KGgo="

function setup() {
  return render(
    <ImageViewerDialog
      target={{ source, title: "图表预览" }}
      onOpenChange={vi.fn()}
    />,
  )
}

function image(): HTMLElement {
  return screen.getByRole("img", { name: "图表预览" })
}

describe("ImageViewerDialog", () => {
  it("rotates the picture a quarter turn with each rotate button", async () => {
    const user = userEvent.setup()
    setup()

    await user.click(screen.getByRole("button", { name: "向右旋转" }))
    expect(image().style.transform).toBe("rotate(90deg)")

    await user.click(screen.getByRole("button", { name: "向右旋转" }))
    expect(image().style.transform).toBe("rotate(180deg)")

    await user.click(screen.getByRole("button", { name: "向左旋转" }))
    expect(image().style.transform).toBe("rotate(90deg)")
  })

  it("offers the picture as a download named after its caption", () => {
    setup()

    const link = screen.getByRole("link", { name: "下载图片" })
    expect(link.getAttribute("href")).toBe(source)
    expect(link.getAttribute("download")).toBe("图表预览.png")
  })

  it("has no reset control so every toolbar button changes the picture", () => {
    setup()

    expect(screen.queryByRole("button", { name: "重置缩放" })).toBeNull()
    expect(screen.getByText("100%")).toBeTruthy()
  })
})

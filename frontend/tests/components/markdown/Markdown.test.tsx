// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import { Markdown } from "@/components/markdown/Markdown"

afterEach(cleanup)

describe("Markdown math", () => {
  it("Markdown renders inline math when a message uses single-dollar delimiters", () => {
    const { container } = render(<Markdown>{String.raw`行内公式 $x_i^2$。`}</Markdown>)

    expect(container.querySelector(".katex")).not.toBeNull()
    expect(container.querySelector(".katex-display")).toBeNull()
    expect(container.textContent).not.toContain("$x_i^2$")
  })

  it("Markdown preserves script positioning when a block formula uses double-dollar delimiters", () => {
    const { container } = render(<Markdown>{"$$\n" + String.raw`\sum_{i=1}^{n}x_i^2+\frac{a}{b}` + "\n$$"}</Markdown>)

    const script = container.querySelector<HTMLElement>(".katex-display .vlist > span")
    expect(script?.style.top).toBeTruthy()
  })

  it("Markdown preserves matrix positioning when a streamed formula finishes", () => {
    const { container, rerender } = render(<Markdown animated isAnimating>{"$$\n" + String.raw`\begin{pmatrix} a & b`}</Markdown>)

    rerender(<Markdown animated isAnimating={false}>{"$$\n" + String.raw`\begin{pmatrix} a & b \\ c & d \end{pmatrix}` + "\n$$"}</Markdown>)

    const column = container.querySelector<HTMLElement>(".katex-display .mtable .vlist")
    expect(column?.style.height).toBeTruthy()
  })
})

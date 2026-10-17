// @vitest-environment jsdom
import { render } from "@testing-library/react"
import { expect, it, vi } from "vitest"

const diagram = vi.hoisted(() => ({ config: undefined as { themeCSS?: string } | undefined }))
vi.mock("streamdown", () => ({ Streamdown: ({ mermaid, children }: { mermaid?: { config?: { themeCSS?: string } }; children: string }) => {
  diagram.config = mermaid?.config
  return <div>{children}</div>
} }))

import { Markdown } from "./index"

it("diagrams inherit theme ink when a markdown message contains a chart", () => {
  render(<Markdown>{"```mermaid\ngraph TD\nA --> B\n```"}</Markdown>)
  expect(diagram.config?.themeCSS).toContain("var(--foreground)")
  expect(diagram.config?.themeCSS).toContain("var(--muted-foreground)")
  expect(diagram.config?.themeCSS).toContain("var(--card)")
})

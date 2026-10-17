// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it } from "vitest"

import { Badge } from "./badge"
import { Bubble, BubbleContent, BubbleReactions } from "./bubble"
import { Button } from "./button"
import { FieldLegend, FieldTitle } from "./field"
import { Label } from "./label"
import { Select, SelectTrigger } from "./select"
import { Table, TableHead, TableHeader, TableRow } from "./table"
import { TooltipProvider } from "./tooltip"

afterEach(cleanup)

describe("SMUI upstream primitives", () => {
  it.each(["default", "outline", "secondary", "ghost", "destructive", "link"] as const)(
    "Button supplies UI typography when the %s variant is selected",
    (variant) => {
      render(<Button variant={variant}>Continue</Button>)
      expect(screen.getByRole("button").classList.contains("text-ui")).toBe(true)
    },
  )

  it.each(["xs", "sm", "icon-xs", "icon-sm"] as const)(
    "Button uses theme radius when the %s size is selected",
    (size) => {
      render(<Button size={size}>Continue</Button>)
      expect(screen.getByRole("button").className).not.toContain("rounded-[")
    },
  )

  it.each([
    ["Label", <Label key="label">Name</Label>],
    ["FieldTitle", <FieldTitle key="title">Name</FieldTitle>],
    ["FieldLegend", <fieldset key="legend"><FieldLegend variant="label">Name</FieldLegend></fieldset>],
  ])("%s supplies the label typography when rendered without call-site styles", (_, element) => {
    render(element)
    expect([...screen.getByText("Name").classList]).toEqual(expect.arrayContaining([
      "text-label", "text-muted-foreground", "uppercase", "tracking-label", "font-normal",
    ]))
  })

  it("Badge supplies uppercase label typography when rendered", () => {
    render(<Badge>Ready</Badge>)
    expect([...screen.getByText("Ready").classList]).toEqual(expect.arrayContaining([
      "text-label", "uppercase", "tracking-label", "rounded-md",
    ]))
  })

  it("TableHead supplies muted label typography when rendered", () => {
    render(<Table><TableHeader><TableRow><TableHead>Name</TableHead></TableRow></TableHeader></Table>)
    expect([...screen.getByRole("columnheader").classList]).toEqual(expect.arrayContaining([
      "text-label", "text-muted-foreground", "uppercase", "tracking-label", "font-normal",
    ]))
  })

  it("Bubble uses shared accent tokens when the tinted variant is selected", () => {
    const { container } = render(<Bubble variant="tinted"><BubbleContent>Hello</BubbleContent></Bubble>)
    const bubble = container.querySelector('[data-slot="bubble"]')!
    expect(bubble.className).toContain("*:data-[slot=bubble-content]:bg-accent")
    expect(bubble.className).toContain("*:data-[slot=bubble-content]:text-accent-foreground")
    expect(bubble.className).not.toMatch(/oklch|color-mix|dark:/)
  })

  it("BubbleReactions uses theme radius when rendered", () => {
    const { container } = render(<BubbleReactions>Like</BubbleReactions>)
    expect(container.firstElementChild!.classList.contains("rounded-md")).toBe(true)
    expect(container.firstElementChild!.classList.contains("rounded-full")).toBe(false)
  })

  it("SelectTrigger uses theme radius when the small size is selected", () => {
    render(<Select><SelectTrigger size="sm">Select</SelectTrigger></Select>)
    expect(screen.getByRole("combobox").className).not.toContain("rounded-[")
  })

  it("Button tooltip keeps its behavior and theme radius when focused", async () => {
    const user = userEvent.setup()
    render(<TooltipProvider><Button tooltip="More information">Help</Button></TooltipProvider>)
    await user.tab()
    expect(await screen.findByRole("tooltip")).toBeTruthy()
    const arrow = document.querySelector('[data-slot="tooltip-content"] svg')!
    expect(arrow.getAttribute("class")).toContain("rounded-sm")
    expect(arrow.getAttribute("class")).not.toContain("rounded-[2px]")
  })
})

// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { Switch } from "@/components/ui/Switch"

it("moves the thumb to the end of the track when it is on", async () => {
  const onCheckedChange = vi.fn()
  const { rerender } = render(
    <Switch aria-label="邮件通知" checked={false} onCheckedChange={onCheckedChange} />,
  )
  const thumb = () => document.querySelector<HTMLElement>('[data-slot="switch-thumb"]')
  expect(thumb()?.style.translate).toBe("var(--switch-thumb-inset)")

  rerender(<Switch aria-label="邮件通知" checked onCheckedChange={onCheckedChange} />)

  expect(thumb()?.style.translate).toContain("calc(")
  expect(screen.getByRole("switch").style.backgroundColor).toBe("var(--switch-track-checked)")
})

it("reports the next state when the user toggles it", async () => {
  const onCheckedChange = vi.fn()
  render(<Switch aria-label="邮件通知" checked={false} onCheckedChange={onCheckedChange} />)

  await userEvent.setup().click(screen.getByRole("switch"))

  expect(onCheckedChange).toHaveBeenCalledWith(true)
})

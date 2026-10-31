// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { TimezonePicker } from "@/components/settings/TimezonePicker"

it("filters the timezone list by what the user types and picks the match", async () => {
  const onChange = vi.fn()
  render(<TimezonePicker value="Asia/Shanghai" onChange={onChange} />)
  const user = userEvent.setup()

  await user.click(screen.getByRole("combobox", { name: "时区" }))
  await user.type(screen.getByLabelText("搜索时区"), "berlin")

  expect(screen.queryByRole("option", { name: "Asia/Shanghai" })).toBeNull()
  await user.click(await screen.findByRole("option", { name: "Europe/Berlin" }))

  expect(onChange).toHaveBeenCalledWith("Europe/Berlin")
})

it("says so when no timezone matches the typed text", async () => {
  render(<TimezonePicker value="Asia/Shanghai" onChange={vi.fn()} />)
  const user = userEvent.setup()

  await user.click(screen.getByRole("combobox", { name: "时区" }))
  await user.type(screen.getByLabelText("搜索时区"), "not a zone")

  expect(await screen.findByText("没有匹配的时区")).toBeTruthy()
})

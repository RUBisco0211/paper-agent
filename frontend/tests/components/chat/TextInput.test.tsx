// @vitest-environment jsdom
import { StrictMode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { TextInput } from "@/components/chat/TextInput"
import { TooltipProvider } from "@/components/ui/Tooltip"

it("keeps the text editable while sending is unavailable", async () => {
  const user = userEvent.setup()
  const send = vi.fn()
  render(<StrictMode><TooltipProvider><TextInput onSend={send} sendDisabled fileProcessor={async () => null} allowedInputTypes={[]} /></TooltipProvider></StrictMode>)
  const input = screen.getByRole("textbox")
  await user.click(input)
  await user.type(input, "请总结这篇文献")
  expect(input.textContent).toBe("请总结这篇文献")
  const submit = screen.getAllByRole("button")[1] as HTMLButtonElement
  expect(submit.disabled).toBe(true)
  await user.keyboard("{Enter}")
  expect(send).not.toHaveBeenCalled()
  expect(input.textContent).toBe("请总结这篇文献")
})

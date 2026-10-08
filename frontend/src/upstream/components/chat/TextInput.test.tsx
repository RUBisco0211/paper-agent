// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"

import { TextInput } from "./TextInput"
import { TooltipProvider } from "@upstream/components/ui/tooltip"

it("keeps the text editable while sending is unavailable", () => {
  const send = vi.fn()
  render(<TooltipProvider><TextInput onSend={send} sendDisabled fileProcessor={async () => null} allowedInputTypes={[]} /></TooltipProvider>)
  const input = screen.getByRole("textbox") as HTMLTextAreaElement
  fireEvent.change(input, { target: { value: "请总结这篇文献" } })
  expect(input.value).toBe("请总结这篇文献")
  const submit = screen.getAllByRole("button")[1] as HTMLButtonElement
  expect(submit.disabled).toBe(true)
  fireEvent.keyDown(input, { key: "Enter" })
  expect(send).not.toHaveBeenCalled()
  expect(input.value).toBe("请总结这篇文献")
})

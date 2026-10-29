// @vitest-environment jsdom
import { StrictMode, createRef } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { MentionInput, type MentionInputRef } from "@/components/chat/MentionInput"

const candidates = [
  { user_paper_id: "p-1", title: "Safe and Scalable Payload Transport" },
  { user_paper_id: "p-2", title: "Beyond Safety Filtering" },
]

function setup() {
  const onChange = vi.fn()
  const onSubmit = vi.fn()
  const ref = createRef<MentionInputRef>()
  render(
    // The app mounts under StrictMode; a second mount must not strand the editor.
    <StrictMode>
      <MentionInput
        ref={ref}
        candidates={candidates}
        placeholder="输入消息"
        onChange={onChange}
        onSubmit={onSubmit}
      />
    </StrictMode>,
  )
  return { onChange, onSubmit, ref, box: screen.getByRole("textbox") }
}

async function insertFirstCandidate(user: ReturnType<typeof userEvent.setup>, box: HTMLElement) {
  await user.click(box)
  await user.type(box, "@scalable")
  await user.click(
    screen.getByRole("option", { name: "Safe and Scalable Payload Transport" }),
  )
}

describe("@ 文献 chip", () => {
  it("offers only the candidates matching the title typed after @", async () => {
    const user = userEvent.setup()
    const { box } = setup()

    await user.click(box)
    await user.type(box, "@scalable")

    expect(
      screen.getByRole("option", { name: "Safe and Scalable Payload Transport" }),
    ).toBeTruthy()
    expect(screen.queryByText("Beyond Safety Filtering")).toBeNull()
  })

  it("inserts the picked paper as a non-editable chip", async () => {
    const user = userEvent.setup()
    const { box } = setup()

    await insertFirstCandidate(user, box)

    const chip = box.querySelector(".composer-mention")
    expect(chip?.getAttribute("contenteditable")).toBe("false")
    expect(chip?.textContent).toBe("@Safe and Scalable Payloa…")
    expect(chip?.getAttribute("title")).toBe("Safe and Scalable Payload Transport")
  })

  it("deletes a chip whole on backspace without leaving the trigger behind", async () => {
    const user = userEvent.setup()
    const { ref, box } = setup()

    await insertFirstCandidate(user, box)
    // The caret sits right after the chip; the browser hands this backspace to
    // ProseMirror, which must drop the whole atom instead of one character.
    ref.current?.editor()?.commands.setTextSelection(2)
    await user.keyboard("{Backspace}")

    expect(box.querySelector(".composer-mention")).toBeNull()
    expect(box.textContent).not.toContain("@")
  })

  it("keeps the picker closed while an IME composition is running", async () => {
    const user = userEvent.setup()
    const { box } = setup()

    await user.click(box)
    fireEvent.compositionStart(box)
    await user.type(box, "@scalable", { skipClick: true })

    expect(box.textContent).toBe("@scalable")
    expect(screen.queryByRole("option")).toBeNull()
  })

  it("leaves Enter to the IME instead of sending mid-composition", async () => {
    const user = userEvent.setup()
    const { box, onSubmit } = setup()

    await user.click(box)
    await user.type(box, "你好")
    fireEvent.keyDown(box, { key: "Enter", isComposing: true })
    expect(onSubmit).not.toHaveBeenCalled()

    await user.keyboard("{Enter}")
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it("reports chips and text in document order", async () => {
    const user = userEvent.setup()
    const { ref, box } = setup()

    await user.type(box, "先看 ")
    await insertFirstCandidate(user, box)
    await user.type(box, "再问")

    expect(ref.current?.read()).toEqual({
      text: "先看 @Safe and Scalable Payload Transport 再问",
      mentions: [candidates[0]],
    })
  })
})

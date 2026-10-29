// @vitest-environment jsdom
import { StrictMode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { TextInput } from "@/components/chat/TextInput"
import { mentionPlaceholders } from "@/lib/mentions"
import { TooltipProvider } from "@/components/ui/Tooltip"

const candidates = [
  { user_paper_id: "p-1", title: "Safe and Scalable Payload Transport" },
  { user_paper_id: "p-2", title: "Beyond Safety Filtering" },
]

function setup() {
  const onSend = vi.fn().mockResolvedValue(undefined)
  const onMentions = vi.fn()
  render(
    <StrictMode>
      <TooltipProvider>
        <TextInput
          onSend={onSend}
          fileProcessor={async () => null}
          allowedInputTypes={[]}
          mentionCandidates={candidates}
          onMentions={onMentions}
        />
      </TooltipProvider>
    </StrictMode>,
  )
  return { onSend, onMentions, box: screen.getByRole("textbox") }
}

describe("@ mentions", () => {
  it("shows the picked paper as a chip inside the composer", async () => {
    const user = userEvent.setup()
    const { box } = setup()

    await user.click(box)
    await user.type(box, "@scalable")
    await user.click(
      screen.getByRole("option", { name: "Safe and Scalable Payload Transport" }),
    )

    const chip = box.querySelector(".composer-mention")
    expect(chip?.getAttribute("contenteditable")).toBe("false")
    expect(chip?.textContent).toBe("@Safe and Scalable Payloa…")
    expect(chip?.getAttribute("title")).toBe("Safe and Scalable Payload Transport")
  })

  it("reports the mentions of the message in document order", async () => {
    const user = userEvent.setup()
    const { onMentions, box } = setup()

    await user.click(box)
    await user.type(box, "@scalable")
    await user.click(
      screen.getByRole("option", { name: "Safe and Scalable Payload Transport" }),
    )

    expect(onMentions).toHaveBeenCalledWith([candidates[0]])
  })

  it("sends the readable titles that the request turns into placeholders", async () => {
    const user = userEvent.setup()
    const { onSend, box } = setup()

    await user.click(box)
    await user.type(box, "@scalable")
    await user.click(
      screen.getByRole("option", { name: "Safe and Scalable Payload Transport" }),
    )
    await user.type(box, "和 ")
    await user.type(box, "@filtering")
    await user.click(
      screen.getByRole("option", { name: "Beyond Safety Filtering" }),
    )
    await user.type(box, "的差别{Enter}")

    expect(onSend).toHaveBeenCalledTimes(1)
    const text = onSend.mock.calls[0][0][0].text as string
    expect(text).toBe(
      "@Safe and Scalable Payload Transport 和 @Beyond Safety Filtering 的差别",
    )
    expect(mentionPlaceholders(text, candidates)).toEqual({
      text: "@{{1}} 和 @{{2}} 的差别",
      mentions: candidates,
    })
  })
})

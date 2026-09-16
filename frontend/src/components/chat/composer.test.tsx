// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"

import { Composer } from "./composer"

function setup(props: Partial<React.ComponentProps<typeof Composer>> = {}) {
  const onSend = vi.fn()
  const onStop = vi.fn()
  const onResume = vi.fn()
  const result = render(
    <MemoryRouter>
      <Composer
        generating={false}
        pendingCount={0}
        llmReady
        busy={false}
        onSend={onSend}
        onStop={onStop}
        onResume={onResume}
        {...props}
      />
    </MemoryRouter>,
  )
  return { ...result, onSend, onStop, onResume }
}

describe("Composer", () => {
  it("sends a plain message when the session is idle", async () => {
    const user = userEvent.setup()
    const { onSend } = setup()

    await user.type(screen.getByRole("textbox"), "这篇论文的核心贡献是什么？")
    await user.click(screen.getByRole("button", { name: /发送/ }))

    expect(onSend).toHaveBeenCalledWith("这篇论文的核心贡献是什么？", undefined)
  })

  it("explains steering and follow-up separately while generating", async () => {
    const user = userEvent.setup()
    const { onSend, onStop } = setup({ generating: true })

    await user.type(screen.getByRole("textbox"), "只看编码器部分")
    await user.click(screen.getByRole("button", { name: /调整当前回答/ }))

    expect(onSend).toHaveBeenCalledWith("只看编码器部分", "steering")
    // The same text must not be shown as both queued and sent.
    expect(screen.queryByRole("button", { name: /发送/ })).toBeNull()

    await user.click(screen.getByRole("button", { name: /停止/ }))
    expect(onStop).toHaveBeenCalled()
  })

  it("offers an explicit resume when queued input is waiting", async () => {
    const user = userEvent.setup()
    const { onResume, onSend } = setup({ pendingCount: 2 })

    expect(screen.getByText(/有 2 条排队消息尚未投递/)).toBeTruthy()
    await user.type(screen.getByRole("textbox"), "继续")
    await user.click(screen.getByRole("button", { name: /继续处理排队消息/ }))

    expect(onResume).toHaveBeenCalled()
    expect(onSend).not.toHaveBeenCalled()
  })

  it("blocks generation without a complete model configuration", async () => {
    const user = userEvent.setup()
    const { onSend } = setup({ llmReady: false })

    await user.type(screen.getByRole("textbox"), "hi")
    await user.click(screen.getByRole("button", { name: /发送/ }))

    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByText(/还没有可用的模型配置/)).toBeTruthy()
  })
})

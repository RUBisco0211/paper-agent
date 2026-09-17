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
  render(
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
  return { onSend, onStop, onResume }
}

describe("Composer", () => {
  it("sends a plain message when the session is idle", async () => {
    const user = userEvent.setup()
    const { onSend } = setup()

    await user.type(screen.getByRole("textbox"), "这篇文献的核心贡献是什么？")
    await user.click(screen.getByRole("button", { name: /发送/ }))

    expect(onSend).toHaveBeenCalledWith("这篇文献的核心贡献是什么？", undefined)
  })

  it("lets the user choose how a message is delivered while generating", async () => {
    const user = userEvent.setup()
    const { onSend, onStop } = setup({ generating: true })

    // 默认投递方式是“调整当前回答”
    await user.type(screen.getByRole("textbox"), "只看编码器部分")
    await user.click(screen.getByRole("button", { name: /发送/ }))
    expect(onSend).toHaveBeenCalledWith("只看编码器部分", "steering")

    await user.click(screen.getByRole("radio", { name: /排队追问/ }))
    await user.type(screen.getByRole("textbox"), "再补一个对比")
    await user.click(screen.getByRole("button", { name: /发送/ }))
    expect(onSend).toHaveBeenLastCalledWith("再补一个对比", "follow_up")

    await user.click(screen.getByRole("button", { name: /停止/ }))
    expect(onStop).toHaveBeenCalled()
  })

  it("offers to continue sending queued messages", async () => {
    const user = userEvent.setup()
    const { onResume } = setup({ pendingCount: 2 })

    await user.click(screen.getByRole("button", { name: /待发送 2 条/ }))

    expect(onResume).toHaveBeenCalled()
  })

  it("blocks sending without a complete model configuration", async () => {
    const user = userEvent.setup()
    const { onSend } = setup({ llmReady: false })

    await user.type(screen.getByRole("textbox"), "hi")
    await user.click(screen.getByRole("button", { name: /发送/ }))

    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByText(/模型设置/)).toBeTruthy()
  })
})

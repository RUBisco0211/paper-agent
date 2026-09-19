// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { Composer } from "./composer"

function setup(props: Partial<React.ComponentProps<typeof Composer>> = {}) {
  const onSend = vi.fn()
  const onStop = vi.fn()
  const onResume = vi.fn()
  const onConfigChange = vi.fn()
  const onAttach = vi.fn(async () => undefined)
  render(
    <MemoryRouter>
      <Composer
        generating={false}
        pendingCount={0}
        llmReady
        busy={false}
        config={{ provider: "openai", model: "gpt-fast", api_key: "sk-test" }}
        providers={[
          {
            id: "openai",
            label: "OpenAI",
            models: [
              { id: "gpt-fast", label: "GPT Fast", reasoning_efforts: ["low", "high"] },
              { id: "gpt-deep", label: "GPT Deep", reasoning_efforts: ["medium", "high"] },
            ],
          },
        ]}
        onConfigChange={onConfigChange}
        onAttach={onAttach}
        onSend={onSend}
        onStop={onStop}
        onResume={onResume}
        {...props}
      />
    </MemoryRouter>,
  )
  return { onSend, onStop, onResume, onConfigChange, onAttach }
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

  it("keeps a newline when Shift+Enter is pressed", async () => {
    const user = userEvent.setup()
    const { onSend } = setup()

    await user.type(screen.getByRole("textbox"), "第一行{shift>}{enter}{/shift}第二行")

    expect(onSend).not.toHaveBeenCalled()
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe(
      "第一行\n第二行",
    )
  })

  it("links to settings when no API key is configured", () => {
    setup({ llmReady: false })

    expect(screen.getByText(/请选择问答模型并填写 API Key/)).toBeTruthy()
    expect(screen.getByRole("link", { name: /前往设置/ }).getAttribute("href")).toBe(
      "/settings",
    )
    expect(screen.getByRole("button", { name: /发送/ }).hasAttribute("disabled")).toBe(
      true,
    )
  })

  it("changes the model and supported thinking effort from the composer", async () => {
    const user = userEvent.setup()
    const { onConfigChange } = setup()

    await user.click(screen.getByRole("button", { name: /GPT Fast/ }))
    await user.click(screen.getByRole("menuitem", { name: /GPT Deep/ }))
    expect(onConfigChange).toHaveBeenCalledWith({
      provider: "openai",
      model: "gpt-deep",
      api_key: "sk-test",
      reasoning_effort: undefined,
    })

    await user.click(screen.getByRole("button", { name: /思考 默认/ }))
    await user.click(screen.getByRole("menuitemradio", { name: "高" }))
    expect(onConfigChange).toHaveBeenLastCalledWith({
      provider: "openai",
      model: "gpt-fast",
      api_key: "sk-test",
      reasoning_effort: "high",
    })
  })

  it("uploads a PDF from the attachment button", async () => {
    const user = userEvent.setup()
    const { onAttach } = setup()
    const pdf = new File(["%PDF-1.7"], "paper.pdf", { type: "application/pdf" })

    await user.upload(screen.getByLabelText("选择 PDF"), pdf)

    expect(onAttach).toHaveBeenCalledWith(pdf)
    expect(await screen.findByText("paper.pdf")).toBeTruthy()
    expect(await screen.findByText("已加入当前范围，正在解析")).toBeTruthy()
  })
})

// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import type { SessionRecord } from "@upstream/api/types"
import { PaperChatPage } from "./PaperChatPage"

const send = vi.fn()
const importState = vi.hoisted(() => ({ messages: [] as Array<{ id: string; role: string; content: unknown[] }>, open: vi.fn() }))
vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api: { sessions: { llmCatalog: async () => ({ providers: [] }) } } }) }))
vi.mock("@/lib/import-queue-context", () => ({ useImportQueue: () => ({ setOpen: importState.open }) }))
vi.mock("@/lib/agent-sessions", () => ({ availableChatModels: async () => [], listBindings: async () => [], sameSessionId: (left: string, right: string) => left === right }))
vi.mock("@upstream/hooks/useMessages", () => ({ useMessages: () => ({ msgs: importState.messages, loading: false, phase: "idle", error: null, reconnecting: false, historyInterrupted: false, send, interrupt: vi.fn(), onUserConfirm: vi.fn() }) }))
vi.mock("@upstream/components/chat/ASMessageBubble", () => ({ ASMessageBubble: () => null }))
vi.mock("@upstream/components/chat/TextInput", () => ({ TextInput: ({ disabled, sendDisabled, onSend }: { disabled: boolean; sendDisabled?: boolean; onSend: (blocks: Array<{ type: "text"; text: string }>) => void }) => <button disabled={disabled} data-send-disabled={sendDisabled} onClick={() => onSend([{ type: "text", text: "继续提问" }])}>发送</button> }))
vi.mock("./BoundCitationSheet", () => ({ BoundCitationSheet: () => null }))

it("allows a follow up message in a scheduled run when its session is loaded", async () => {
  importState.messages = []
  send.mockClear()
  const user = userEvent.setup()
  const run = {
    id: "run-1", agent_id: "agent-1", source_schedule_id: "task-1",
    config: { name: "问候", chat_model_config: { type: "deepseek_credential", credential_id: "credential-1", model: "deepseek-chat", parameters: {} } },
  }
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><PaperChatPage scheduledRun={run as SessionRecord} scheduledScope="全局" /></MemoryRouter></QueryClientProvider>)
  expect(screen.getAllByRole("banner")).toHaveLength(1)
  expect(screen.getByRole("link", { name: "返回月视图" })).toBeTruthy()
  expect(document.querySelector('[data-slot="message-scroller-viewport"]')?.className).toContain("no-scrollbar")
  await user.click(screen.getByRole("button", { name: "发送" }))
  expect(send).toHaveBeenCalledWith([{ type: "text", text: "继续提问" }])
})

it("opens the import queue only after the import tool succeeds", () => {
  importState.messages = []
  importState.open.mockClear()
  const run = {
    id: "run-1", agent_id: "agent-1", source_schedule_id: "task-1",
    config: { name: "问候", chat_model_config: { type: "deepseek_credential", credential_id: "credential-1", model: "deepseek-chat", parameters: {} } },
  }
  const queryClient = createQueryClient()
  const page = () => <QueryClientProvider client={queryClient}><MemoryRouter><PaperChatPage scheduledRun={run as SessionRecord} scheduledScope="全局" /></MemoryRouter></QueryClientProvider>
  const { rerender } = render(page())
  importState.messages = [{ id: "message-1", role: "assistant", content: [{ type: "tool_call", id: "call-1", name: "import_selected_papers" }] }]
  rerender(page())
  expect(importState.open).not.toHaveBeenCalled()
  importState.messages = [{ id: "message-1", role: "assistant", content: [
    { type: "tool_call", id: "call-1", name: "import_selected_papers" },
    { type: "tool_result", id: "call-1", state: "error", output: "failed" },
  ] }]
  rerender(page())
  expect(importState.open).not.toHaveBeenCalled()
  importState.messages = [{ id: "message-1", role: "assistant", content: [
    { type: "tool_call", id: "call-1", name: "import_selected_papers" },
    { type: "tool_result", id: "call-1", state: "success", output: "{}" },
  ] }]
  rerender(page())
  expect(importState.open).toHaveBeenCalledWith(true)
})

it("keeps the composer editable while a session model is unavailable", () => {
  importState.messages = []
  const run = { id: "run-1", agent_id: "agent-1", source_schedule_id: "task-1", config: { name: "未配置" } }
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><PaperChatPage scheduledRun={run as SessionRecord} scheduledScope="全局" /></MemoryRouter></QueryClientProvider>)
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(false)
  expect(screen.getByRole("button", { name: "发送" }).getAttribute("data-send-disabled")).toBe("true")
})

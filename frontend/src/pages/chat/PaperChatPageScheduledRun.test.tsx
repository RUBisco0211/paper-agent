// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import type { SessionRecord } from "@/types/agent"
import { PaperChatPage } from "./PaperChatPage"

const send = vi.fn()
const onExternalAnswer = vi.fn(async () => {})
const importState = vi.hoisted(() => ({ messages: [] as Array<{ id: string; role: string; content: unknown[] }>, open: vi.fn(), confirm: vi.fn(async () => {}) }))
vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api: { sessions: { llmCatalog: async () => ({ providers: [] }) }, client: { request: async () => ({ candidates: [{ title: "Selected Study", identifier: "10.1234/selected", source_id: "https://example.org/study" }] }) } } }) }))
vi.mock("@/components/providers/ImportQueueProvider", () => ({ useImportQueue: () => ({ setOpen: importState.open }) }))
vi.mock("@/lib/agentSessions", () => ({ availableChatModels: async () => [], listBindings: async () => [], sameSessionId: (left: string, right: string) => left === right }))
vi.mock("@/hooks/useMessages", () => ({ useMessages: () => ({ msgs: importState.messages, loading: false, phase: "idle", error: null, reconnecting: false, historyInterrupted: false, send, interrupt: vi.fn(), onUserConfirm: importState.confirm, onExternalAnswer }) }))
vi.mock("@/components/chat/MessageBubble", () => ({ MessageBubble: () => null }))
vi.mock("@/components/chat/TextInput", () => ({ TextInput: ({ disabled, sendDisabled, onSend }: { disabled: boolean; sendDisabled?: boolean; onSend: (blocks: Array<{ type: "text"; text: string }>) => void }) => <button disabled={disabled} data-send-disabled={sendDisabled} onClick={() => onSend([{ type: "text", text: "继续提问" }])}>发送</button> }))
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

it("shows a submitted ask-user call even while its tool result is running", async () => {
  onExternalAnswer.mockClear()
  importState.messages = [{ id: "reply-1", role: "assistant", content: [
    { type: "tool_call", id: "call-1", name: "ask_user", state: "submitted", input: JSON.stringify({ questions: [{ name: "scope", prompt: "检索范围？", type: "text" }] }) },
    { type: "tool_result", id: "call-1", name: "ask_user", state: "running", output: "" },
  ] }]
  const run = { id: "run-1", agent_id: "agent-1", source_schedule_id: "task-1", config: { name: "问候" } }
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><PaperChatPage scheduledRun={run as SessionRecord} scheduledScope="全局" /></MemoryRouter></QueryClientProvider>)

  expect(screen.getByText("检索范围？")).toBeTruthy()
  await userEvent.type(screen.getByRole("textbox", { name: "填写答案" }), "当前项目")
  await userEvent.click(screen.getByRole("button", { name: "提交答案" }))
  expect(onExternalAnswer).toHaveBeenCalledWith(expect.objectContaining({ id: "call-1" }), "reply-1", { scope: "当前项目" })
})

it("keeps an import call pending after closing review and confirms only inside the dialog", async () => {
  importState.confirm.mockClear()
  importState.messages = [{ id: "reply-1", role: "assistant", content: [
    { type: "tool_call", id: "call-1", name: "import_selected_papers", state: "asking", input: "{}" },
  ] }]
  const run = { id: "run-1", agent_id: "agent-1", source_schedule_id: "task-1", config: { name: "问候" } }
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><PaperChatPage scheduledRun={run as SessionRecord} scheduledScope="全局" /></MemoryRouter></QueryClientProvider>)

  await userEvent.click(screen.getByRole("button", { name: "查看并确认" }))
  expect(await screen.findByText("Selected Study")).toBeTruthy()
  await userEvent.click(screen.getByRole("button", { name: "关闭" }))
  expect(screen.getByText("文献入库等待确认")).toBeTruthy()
  expect(importState.confirm).not.toHaveBeenCalled()

  await userEvent.click(screen.getByRole("button", { name: "查看并确认" }))
  await userEvent.click(screen.getByRole("button", { name: "确认入库" }))
  expect(importState.confirm).toHaveBeenCalledWith(expect.objectContaining({ id: "call-1" }), true, "reply-1")
})

it("schedule review resumes the same tool with the actual notification choice when the user edits the draft", async () => {
  importState.confirm.mockClear()
  importState.messages = [{ id: "reply-task", role: "assistant", content: [
    { type: "tool_call", id: "call-task", name: "create_scheduled_task", state: "asking", input: JSON.stringify({ name: "初稿", prompt: "总结", time: "09:00", notify_email: true }) },
  ] }]
  const run = { id: "run-1", agent_id: "agent-1", source_schedule_id: "task-1", config: { name: "问候" } }
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><PaperChatPage scheduledRun={run as SessionRecord} scheduledScope="全局" /></MemoryRouter></QueryClientProvider>)
  await userEvent.click(screen.getByRole("button", { name: "查看并确认" }))
  expect(screen.getByRole("checkbox", { name: "邮件通知" }).getAttribute("aria-checked")).toBe("true")
  await userEvent.click(screen.getByRole("checkbox", { name: "邮件通知" }))
  await userEvent.click(screen.getByRole("button", { name: "确认创建" }))
  expect(importState.confirm).toHaveBeenCalledWith(expect.objectContaining({ id: "call-task", name: "create_scheduled_task", input: JSON.stringify({ name: "初稿", prompt: "总结", time: "09:00", weekdays: ["sun", "mon", "tue", "wed", "thu", "fri", "sat"], notify_email: false }) }), true, "reply-task")
})

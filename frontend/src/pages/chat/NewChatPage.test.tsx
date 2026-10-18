// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { NewChatPage } from "./NewChatPage"

const actions = vi.hoisted(() => ({ create: vi.fn(), trigger: vi.fn() }))
vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api: { projects: { list: async () => ({ items: [{ id: "project-1", name: "测试项目" }] }) }, sessions: { llmCatalog: async () => ({ providers: [] }) } } }) }))
vi.mock("@/lib/agentSessions", () => ({
  availableChatModels: async () => [{ type: "deepseek_credential", credential_id: "key-1", model: "deepseek-chat", parameters: {} }],
  createBoundSession: (...args: unknown[]) => actions.create(...args),
}))
vi.mock("@/lib/api/agentscope/chat", () => ({ chatApi: { trigger: (...args: unknown[]) => actions.trigger(...args) } }))
vi.mock("@/components/chat/TextInput", () => ({ TextInput: ({ onSend, sendDisabled }: { onSend: (blocks: unknown[]) => void; sendDisabled: boolean }) => <button disabled={sendDisabled} onClick={() => onSend([{ id: "block-1", type: "text", text: "比较这两篇文献", created_at: "2026-10-08T00:00:00Z" }])}>发送首条消息</button> }))

function Path() { return <span data-testid="path">{useLocation().pathname}</span> }

it("creates a project session only when the first message is sent", async () => {
  actions.create.mockReset().mockResolvedValue({ agentId: "agent-1", sessionId: "session-1" })
  actions.trigger.mockReset().mockResolvedValue({ status: "accepted" })
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={[{ pathname: "/chat/new", state: { initialProjectId: "project-1" } }]}><Routes>
    <Route path="/chat/new" element={<><NewChatPage /><Path /></>} />
    <Route path="/chat/:agentId/:sessionId" element={<Path />} />
  </Routes></MemoryRouter></QueryClientProvider>)
  expect(actions.create).not.toHaveBeenCalled()
  const button = await screen.findByRole("button", { name: "发送首条消息" })
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(button)
  await waitFor(() => expect(actions.create).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ projectId: "project-1" })))
  await waitFor(() => expect(actions.trigger).toHaveBeenCalledWith(expect.objectContaining({ agent_id: "agent-1", session_id: "session-1" })))
  await waitFor(() => expect(screen.getByTestId("path").textContent).toBe("/chat/agent-1/session-1"))
})

it("retries the first message in the same session after a trigger failure", async () => {
  actions.create.mockReset().mockResolvedValue({ agentId: "agent-1", sessionId: "session-1" })
  actions.trigger.mockReset().mockRejectedValueOnce(new Error("网络暂不可用")).mockResolvedValue({ status: "accepted" })
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={["/chat/new"]}><Routes>
    <Route path="/chat/new" element={<><NewChatPage /><Path /></>} />
    <Route path="/chat/:agentId/:sessionId" element={<Path />} />
  </Routes></MemoryRouter></QueryClientProvider>)
  const button = await screen.findByRole("button", { name: "发送首条消息" })
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(button)
  const retry = await screen.findByRole("button", { name: "重试发送" })
  fireEvent.click(retry)
  await waitFor(() => expect(actions.trigger).toHaveBeenCalledTimes(2))
  expect(actions.create).toHaveBeenCalledTimes(1)
  await waitFor(() => expect(screen.getByTestId("path").textContent).toBe("/chat/agent-1/session-1"))
})

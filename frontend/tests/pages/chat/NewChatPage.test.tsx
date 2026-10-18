// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Outlet, Route, Routes, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { NewChatPage } from "@/pages/chat/NewChatPage"

const actions = vi.hoisted(() => ({ create: vi.fn(), trigger: vi.fn(), name: vi.fn() }))
vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api: { projects: { list: async () => ({ items: [{ id: "project-1", name: "测试项目", description: "项目简介" }] }) }, sessions: { llmCatalog: async () => ({ providers: [] }) } } }) }))
vi.mock("@/lib/agentSessions", () => ({
  availableChatModels: async () => [{ type: "deepseek_credential", credential_id: "key-1", model: "deepseek-chat", parameters: {} }],
  createBoundSession: (...args: unknown[]) => actions.create(...args),
  sameSessionId: (left: string, right: string) => left === right,
}))
vi.mock("@/lib/api/agentscope/chat", () => ({ chatApi: { trigger: (...args: unknown[]) => actions.trigger(...args) } }))
vi.mock("@/lib/api/agentscope/session", () => ({ sessionApi: { generateName: (...args: unknown[]) => actions.name(...args) } }))
vi.mock("@/components/chat/TextInput", () => ({ TextInput: ({ onSend, sendDisabled }: { onSend: (blocks: unknown[]) => void; sendDisabled: boolean }) => <button disabled={sendDisabled} onClick={() => onSend([{ id: "block-1", type: "text", text: "比较这两篇文献", created_at: "2026-10-08T00:00:00Z" }])}>发送首条消息</button> }))

function Path() { return <span data-testid="path">{useLocation().pathname}</span> }
function DraftLayout() {
  const location = useLocation()
  const projectId = (location.state as { initialProjectId?: string | null } | null)?.initialProjectId ?? ""
  return <Outlet context={{ draftQuoteKey: `draft:${location.key}:${projectId || "global"}`, draftProjectId: projectId, setDraftProjectId: () => {} }} />
}

it("creates a project session only when the first message is sent", async () => {
  actions.create.mockReset().mockResolvedValue({ agentId: "agent-1", sessionId: "session-1" })
  actions.trigger.mockReset().mockResolvedValue({ status: "accepted" })
  actions.name.mockReset().mockResolvedValue({ name: "RAG 方法比较" })
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={[{ pathname: "/chat/new", state: { initialProjectId: "project-1" } }]}><Routes>
    <Route element={<DraftLayout />}>
      <Route path="/chat/new" element={<><NewChatPage /><Path /></>} />
    </Route>
    <Route path="/chat/:agentId/:sessionId" element={<Path />} />
  </Routes></MemoryRouter></QueryClientProvider>)
  expect(actions.create).not.toHaveBeenCalled()
  const button = await screen.findByRole("button", { name: "发送首条消息" })
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(button)
  await waitFor(() => expect(actions.create).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ projectId: "project-1" })))
  await waitFor(() => expect(actions.trigger).toHaveBeenCalledWith(expect.objectContaining({ agent_id: "agent-1", session_id: "session-1" })))
  await waitFor(() => expect(screen.getByTestId("path").textContent).toBe("/chat/agent-1/session-1"))
  expect(actions.name).toHaveBeenCalledWith("session-1", expect.objectContaining({ agent_id: "agent-1", text: "比较这两篇文献", excerpts: [], project_name: "测试项目", project_description: "项目简介" }))
})

it("retries the first message in the same session after a trigger failure", async () => {
  actions.create.mockReset().mockResolvedValue({ agentId: "agent-1", sessionId: "session-1" })
  actions.trigger.mockReset().mockRejectedValueOnce(new Error("网络暂不可用")).mockResolvedValue({ status: "accepted" })
  actions.name.mockReset().mockResolvedValue({ name: "RAG 方法比较" })
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={["/chat/new"]}><Routes>
    <Route element={<DraftLayout />}>
      <Route path="/chat/new" element={<><NewChatPage /><Path /></>} />
    </Route>
    <Route path="/chat/:agentId/:sessionId" element={<Path />} />
  </Routes></MemoryRouter></QueryClientProvider>)
  const button = await screen.findByRole("button", { name: "发送首条消息" })
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(button)
  const retry = await screen.findByRole("button", { name: "重试发送" })
  fireEvent.click(retry)
  await waitFor(() => expect(actions.trigger).toHaveBeenCalledTimes(2))
  expect(actions.create).toHaveBeenCalledTimes(1)
  expect(actions.name).toHaveBeenCalledTimes(1)
  await waitFor(() => expect(screen.getByTestId("path").textContent).toBe("/chat/agent-1/session-1"))
})

it("navigates before the generated name arrives and then replaces the cached name", async () => {
  const queryClient = createQueryClient()
  queryClient.setQueryData(["bound-sessions"], [{ agentId: "agent-1", session: { session: { id: "session-1", config: { name: "2026-10-19 10:00:00" } } }, binding: { session_id: "session-1", project_id: null, scope: "library" } }] as never)
  queryClient.setQueryData(["agent-sessions", "agent-1"], { sessions: [{ session: { id: "session-1", config: { name: "2026-10-19 10:00:00" } } }], total: 1 } as never)
  let resolveName: (value: { name: string }) => void = () => {}
  actions.create.mockReset().mockResolvedValue({ agentId: "agent-1", sessionId: "session-1" })
  actions.trigger.mockReset().mockResolvedValue({ status: "accepted" })
  actions.name.mockReset().mockReturnValue(new Promise((resolve) => { resolveName = resolve }))
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={["/chat/new"]}><Routes>
    <Route element={<DraftLayout />}>
      <Route path="/chat/new" element={<><NewChatPage /><Path /></>} />
    </Route>
    <Route path="/chat/:agentId/:sessionId" element={<Path />} />
  </Routes></MemoryRouter></QueryClientProvider>)
  const button = await screen.findByRole("button", { name: "发送首条消息" })
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(button)
  await waitFor(() => expect(actions.trigger).toHaveBeenCalled())
  await waitFor(() => expect(screen.getByTestId("path").textContent).toBe("/chat/agent-1/session-1"))
  resolveName({ name: "RAG 方法比较" })
  await waitFor(() => {
    const bound = queryClient.getQueryData(["bound-sessions"]) as Array<{ session: { session: { config: { name: string } } } }>
    expect(bound[0].session.session.config.name).toBe("RAG 方法比较")
  })
})

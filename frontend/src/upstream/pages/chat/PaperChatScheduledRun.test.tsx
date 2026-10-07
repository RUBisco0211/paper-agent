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
vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api: { sessions: { llmCatalog: async () => ({ providers: [] }) } } }) }))
vi.mock("@/lib/agent-sessions", () => ({ availableChatModels: async () => [], listBindings: async () => [], sameSessionId: (left: string, right: string) => left === right }))
vi.mock("@upstream/hooks/useMessages", () => ({ useMessages: () => ({ msgs: [], loading: false, phase: "idle", error: null, reconnecting: false, historyInterrupted: false, send, interrupt: vi.fn(), onUserConfirm: vi.fn() }) }))
vi.mock("@upstream/components/chat/TextInput", () => ({ TextInput: ({ disabled, onSend }: { disabled: boolean; onSend: (blocks: Array<{ type: "text"; text: string }>) => void }) => <button disabled={disabled} onClick={() => onSend([{ type: "text", text: "继续提问" }])}>发送</button> }))
vi.mock("./BoundCitationSheet", () => ({ BoundCitationSheet: () => null }))

it("allows a follow up message in a scheduled run when its session is loaded", async () => {
  send.mockClear()
  const user = userEvent.setup()
  const run = {
    id: "run-1", agent_id: "agent-1", source_schedule_id: "task-1",
    config: { name: "问候", chat_model_config: { type: "deepseek_credential", credential_id: "credential-1", model: "deepseek-chat", parameters: {} } },
  }
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><PaperChatPage scheduledRun={run as SessionRecord} scheduledScope="全局" /></MemoryRouter></QueryClientProvider>)
  await user.click(screen.getByRole("button", { name: "发送" }))
  expect(send).toHaveBeenCalledWith([{ type: "text", text: "继续提问" }])
})

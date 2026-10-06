import { expect, it } from "vitest"
import { chatPath, mostRecentSession, reasoningEffortsForModel } from "./chat-view"

it("opens the newest bound session when the conversation route has no session", () => {
  const sessions = [
    { agentId: "agent-a", session: { session: { id: "older", created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-03T00:00:00Z" } } },
    { agentId: "agent-b", session: { session: { id: "newer", created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z" } } },
  ]
  expect(chatPath(mostRecentSession(sessions))).toBe("/chat/agent-a/older")
})

it("shows only catalog supported reasoning efforts for the chosen model", () => {
  const providers = [{ id: "deepseek", models: [
    { id: "flash", reasoning_efforts: [] },
    { id: "pro", reasoning_efforts: ["low", "high"] },
  ] }]
  expect(reasoningEffortsForModel(providers, "deepseek_credential", "pro")).toEqual(["low", "high"])
  expect(reasoningEffortsForModel(providers, "deepseek_credential", "flash")).toEqual([])
})

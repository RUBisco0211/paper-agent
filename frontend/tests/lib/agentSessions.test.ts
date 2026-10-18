import { beforeEach, describe, expect, it, vi } from "vitest"

const agent = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
}))
const credential = vi.hoisted(() => ({ list: vi.fn() }))
const session = vi.hoisted(() => ({ create: vi.fn(), delete: vi.fn(), list: vi.fn() }))

vi.mock("@/lib/api/agentscope/agent", () => ({ agentApi: agent }))
vi.mock("@/lib/api/agentscope/credential", () => ({ credentialApi: credential }))
vi.mock("@/lib/api/agentscope/session", () => ({ sessionApi: session }))

import { createBoundSession, deleteBoundSession, deleteProjectWithSessions, listBoundSessions, sameSessionId } from "@/lib/agentSessions"
import { ApiError as AgentApiError } from "@/lib/api/agentscope/client"

describe("bound AgentScope session creation", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    agent.list.mockResolvedValue({ agents: [{ id: "agent-1" }] })
    credential.list.mockResolvedValue({ credentials: [{ id: "credential-1", data: { type: "openai_credential" } }] })
    session.create.mockResolvedValue({ session_id: "session-1" })
    session.delete.mockResolvedValue(undefined)
  })

  it("binds the project before exposing a newly created session", async () => {
    const request = vi.fn().mockResolvedValue({ session_id: "session-1" })
    const api = {
      sessions: { llmCatalog: vi.fn().mockResolvedValue({ providers: [{ id: "openai", models: [{ id: "gpt-4o" }] }] }) },
      client: { request },
    }

    const result = await createBoundSession(api as never, { projectId: "project-1" })

    expect(session.create).toHaveBeenCalledWith({
      agent_id: "agent-1",
      chat_model_config: { type: "openai_credential", credential_id: "credential-1", model: "gpt-4o", parameters: {} },
    })
    expect(request).toHaveBeenCalledWith("/v1/session-bindings", {
      method: "POST", json: { session_id: "session-1", project_id: "project-1" },
    })
    expect(result).toEqual({ agentId: "agent-1", sessionId: "session-1" })
  })

  it("removes the AgentScope session when the business binding fails", async () => {
    const api = {
      sessions: { llmCatalog: vi.fn().mockResolvedValue({ providers: [{ id: "openai", models: [{ id: "gpt-4o" }] }] }) },
      client: { request: vi.fn().mockRejectedValue(new Error("binding failed")) },
    }

    await expect(createBoundSession(api as never, {})).rejects.toThrow("binding failed")
    expect(session.delete).toHaveBeenCalledWith("session-1", "agent-1")
  })
})

describe("bound AgentScope session listing", () => {
  beforeEach(() => vi.clearAllMocks())

  it("joins a business UUID to an AgentScope session when their formats differ", async () => {
    const rawId = "11111111111111111111111111111111"
    agent.list.mockResolvedValue({ agents: [{ id: "agent-1" }] })
    session.list.mockResolvedValue({ sessions: [{ session: { id: rawId, created_at: "2026-10-06T00:00:00Z" } }] })
    const api = { client: { request: vi.fn().mockResolvedValue({
      items: [{ session_id: "11111111-1111-1111-1111-111111111111", project_id: "project-1", scope: "project" }],
      total: 1,
    }) } }

    const listed = await listBoundSessions(api as never)

    expect(listed).toHaveLength(1)
    expect(listed[0]?.binding.scope).toBe("project")
    expect(sameSessionId(listed[0]!.binding.session_id, rawId)).toBe(true)
  })
})

describe("bound AgentScope session deletion", () => {
  beforeEach(() => vi.clearAllMocks())

  it("removes the AgentScope session before removing its business binding", async () => {
    const calls: string[] = []
    session.delete.mockImplementation(async () => { calls.push("agent") })
    const request = vi.fn(async () => { calls.push("binding") })

    await deleteBoundSession({ client: { request } } as never, {
      agentId: "agent-1", sessionId: "session-1",
    })

    expect(calls).toEqual(["agent", "binding"])
    expect(request).toHaveBeenCalledWith("/v1/session-bindings/session-1", { method: "DELETE" })
  })

  it("cleans the business binding when the AgentScope session is already absent", async () => {
    session.delete.mockRejectedValue(new AgentApiError(404, "Not found"))
    const request = vi.fn().mockResolvedValue(undefined)

    await deleteBoundSession({ client: { request } } as never, {
      agentId: "agent-1", sessionId: "session-1",
    })

    expect(request).toHaveBeenCalledOnce()
  })

  it("keeps the business binding when AgentScope deletion fails", async () => {
    session.delete.mockRejectedValue(new AgentApiError(503, "Unavailable"))
    const request = vi.fn()

    await expect(deleteBoundSession({ client: { request } } as never, {
      agentId: "agent-1", sessionId: "session-1",
    })).rejects.toThrow("Unavailable")

    expect(request).not.toHaveBeenCalled()
  })
})

describe("project deletion", () => {
  beforeEach(() => vi.clearAllMocks())

  it("removes bound AgentScope sessions before deleting their project", async () => {
    const calls: string[] = []
    agent.list.mockResolvedValue({ agents: [{ id: "agent-1" }] })
    session.list.mockResolvedValue({ sessions: [{ session: { id: "11111111111111111111111111111111", created_at: "2026-10-06T00:00:00Z" } }] })
    session.delete.mockImplementation(async () => { calls.push("agent") })
    const request = vi.fn(async (path: string) => {
      if (path === "/v1/session-bindings") return {
        items: [{ session_id: "11111111-1111-1111-1111-111111111111", project_id: "project-1", scope: "project" }], total: 1,
      }
      calls.push("binding")
      return undefined
    })
    const remove = vi.fn(async () => { calls.push("project") })

    await deleteProjectWithSessions({ client: { request }, projects: { remove } } as never, "project-1")

    expect(calls).toEqual(["agent", "binding", "project"])
  })
})

import { afterEach, describe, expect, it, vi } from "vitest"

import { client, configureAgentClient } from "./client"

describe("AgentScope client authentication", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("sends the shared bearer token when requesting a session", async () => {
    const request = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ items: [] }), { status: 200 }),
    )
    vi.stubGlobal("fetch", request)
    configureAgentClient({
      baseUrl: "http://127.0.0.1:8001",
      getAccessToken: () => "access-token",
      refreshAccessToken: async () => "renewed-token",
    })

    await client.get("/sessions/")

    const init = request.mock.calls[0]?.[1]
    expect(init?.headers).toEqual({ Authorization: "Bearer access-token" })
  })

  it("retries with a refreshed token when the access token expires", async () => {
    let token = "expired"
    const request = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ items: [] }), { status: token === "expired" ? 401 : 200 }),
    )
    vi.stubGlobal("fetch", request)
    configureAgentClient({
      baseUrl: "http://127.0.0.1:8001",
      getAccessToken: () => token,
      refreshAccessToken: async () => { token = "renewed"; return token },
    })

    await client.get("/sessions/")

    expect(request).toHaveBeenCalledTimes(2)
    expect(request.mock.calls[1]?.[1]?.headers).toEqual({ Authorization: "Bearer renewed" })
  })

  it("preserves an authentication failure when refresh fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 401 })))
    configureAgentClient({
      baseUrl: "http://127.0.0.1:8001",
      getAccessToken: () => "expired",
      refreshAccessToken: async () => { throw new Error("会话已过期，请重新登录") },
    })

    await expect(client.get("/sessions/", undefined, { silent: true })).rejects.toThrow("会话已过期，请重新登录")
  })

  it("does not send the access token to an overridden server address", async () => {
    const request = vi.fn()
    vi.stubGlobal("fetch", request)
    configureAgentClient({
      baseUrl: "http://127.0.0.1:8001",
      getAccessToken: () => "private-token",
      refreshAccessToken: async () => "renewed-token",
    })

    await expect(client.get("/sessions/", undefined, { baseUrl: "https://other.example" })).rejects.toThrow()
    expect(request).not.toHaveBeenCalled()
  })
})

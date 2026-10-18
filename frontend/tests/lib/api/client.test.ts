import { describe, expect, it, vi } from "vitest"

import { ApiClient } from "@/lib/api/client"
import { createApi } from "@/lib/api/index"
import { ApiError } from "@/lib/api/errors"

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

describe("ApiClient", () => {
  it("attaches the bearer token and parses the payload", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ id: "p1", title: "Attention" }),
    )
    const client = new ApiClient({
      baseUrl: "https://api.test",
      getAccessToken: () => "token-1",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    const paper = await client.request<{ id: string; title: string }>(
      "/v1/papers/p1",
    )

    expect(paper.title).toBe("Attention")
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe("https://api.test/v1/papers/p1")
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer token-1",
    )
    expect(init.credentials).toBe("include")
  })

  it("serializes JSON bodies and skips empty query values", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ok: true }))
    const client = new ApiClient({
      baseUrl: "https://api.test",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    await client.request("/v1/papers", {
      method: "POST",
      json: { name: "Reading" },
      query: { limit: 20, q: undefined, project_id: null },
    })

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe("https://api.test/v1/papers?limit=20")
    expect(init.method).toBe("POST")
    expect(init.body).toBe(JSON.stringify({ name: "Reading" }))
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    )
  })

  it("maps error bodies into typed failures", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(
        {
          code: "paper_not_found",
          message: "论文不存在",
          request_id: "req-1",
        },
        404,
      ),
    )
    const client = new ApiClient({
      baseUrl: "https://api.test",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    const failure = await client.request("/v1/papers/missing").catch((error) => error)

    expect(failure).toBeInstanceOf(ApiError)
    const error = failure as ApiError
    expect(error.status).toBe(404)
    expect(error.code).toBe("paper_not_found")
    expect(error.message).toBe("论文不存在")
    expect(error.requestId).toBe("req-1")
    expect(error.isNotAllowed).toBe(true)
  })

  it("classifies validation and provider failures differently", () => {
    expect(new ApiError(422, { code: "validation_error" }).isValidation).toBe(true)
    expect(new ApiError(503, { code: "provider_unavailable" }).isUnavailable).toBe(
      true,
    )
    expect(new ApiError(401, { code: "unauthorized" }).isUnauthorized).toBe(true)
  })

  it("refreshes once for concurrent 401 responses and retries each request", async () => {
    let token = "expired"
    const calls: string[] = []
    let refreshCount = 0

    const fetchImpl = vi.fn(async (input: string | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(url)
      if (url.endsWith("/v1/auth/refresh")) {
        refreshCount += 1
        token = "fresh"
        return jsonResponse({
          access_token: "fresh",
          token_type: "bearer",
          expires_in: 900,
          expires_at: new Date(Date.now() + 900_000).toISOString(),
        })
      }
      const header = (init?.headers as Record<string, string>).Authorization
      return header === "Bearer fresh"
        ? jsonResponse({ ok: true })
        : jsonResponse({ code: "unauthorized", message: "登录态已失效" }, 401)
    })

    const client = new ApiClient({
      baseUrl: "https://api.test",
      getAccessToken: () => token,
      onAccessToken: (session) => {
        token = session?.access_token ?? ""
      },
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    const results = await Promise.all([
      client.request("/v1/papers"),
      client.request("/v1/projects"),
    ])

    expect(results).toEqual([{ ok: true }, { ok: true }])
    expect(refreshCount).toBe(1)
    expect(calls.filter((url) => url.endsWith("/refresh"))).toHaveLength(1)
    // Each failed request is retried exactly once with the fresh token.
    expect(calls.filter((url) => url.endsWith("/v1/papers"))).toHaveLength(2)
  })

  it("surfaces a failed refresh without retrying forever", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) =>
      String(input).endsWith("/refresh")
        ? jsonResponse(
            { code: "refresh_token_reused", message: "检测到刷新令牌重复使用" },
            401,
          )
        : jsonResponse({ code: "unauthorized", message: "登录态已失效" }, 401),
    )
    const client = new ApiClient({
      baseUrl: "https://api.test",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    const failure = await client.request("/v1/papers").catch((error) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect((failure as ApiError).code).toBe("refresh_token_reused")
    expect(fetchImpl).toHaveBeenCalledTimes(2)
  })

  it("does not attempt a refresh for login and register", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ code: "invalid_credentials", message: "邮箱或密码不正确" }, 401),
    )
    const client = new ApiClient({
      baseUrl: "https://api.test",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    const failure = await client
      .request("/v1/auth/login", { method: "POST", json: {} })
      .catch((error) => error)

    expect((failure as ApiError).code).toBe("invalid_credentials")
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })
})

describe("AgentScope API connection", () => {
  it("shares the business token and refreshes it through the business origin", async () => {
    let token = "expired"
    const calls: Array<[string, RequestInit | undefined]> = []
    const fetchImpl = vi.fn(async (input: string | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push([url, init])
      if (url === "https://business.test/v1/auth/refresh") {
        token = "fresh"
        return jsonResponse({
          access_token: token,
          token_type: "bearer",
          expires_in: 900,
          expires_at: new Date(Date.now() + 900_000).toISOString(),
        })
      }
      return (init?.headers as Record<string, string>).Authorization ===
        "Bearer fresh"
        ? jsonResponse({ agents: [], total: 0 })
        : jsonResponse({ detail: "invalid_access_token" }, 401)
    })
    const api = createApi({
      baseUrl: "https://business.test",
      agentServiceBaseUrl: "https://agent.test",
      getAccessToken: () => token,
      onAccessToken: (session) => { token = session?.access_token ?? "" },
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    const agents = await api.agentService.request<{ agents: unknown[] }>("/agent/")

    expect(agents.agents).toEqual([])
    expect(calls.map(([url]) => url)).toEqual([
      "https://agent.test/agent/",
      "https://business.test/v1/auth/refresh",
      "https://agent.test/agent/",
    ])
    expect((calls[2][1]?.headers as Record<string, string>).Authorization).toBe(
      "Bearer fresh",
    )
    expect(calls[2][1]?.credentials).toBe("omit")
  })
})

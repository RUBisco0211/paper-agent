import { describe, expect, it, vi } from "vitest"

import { ApiClient } from "./client"
import { ApiError } from "./errors"
import { streamSessionEvents } from "./sse"

const SESSION_ID = "11111111-1111-4111-8111-111111111111"

function sseResponse(body: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body))
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  })
}

const STREAM = [
  "event: generation.started",
  'data: {"event_id":"1","type":"generation.started","resource_id":"s1","sequence":1,"timestamp":"2026-09-17T00:00:00Z","schema_version":1,"data":{"model":"gpt-x"}}',
  "id: 1",
  "",
  ": keep-alive",
  "",
  "event: message.delta",
  'data: {"event_id":"2","type":"message.delta","resource_id":"s1","sequence":2,"timestamp":"2026-09-17T00:00:01Z","schema_version":1,"data":{"text":"attention"}}',
  "id: 2",
  "",
  "event: generation.failed",
  'data: {"event_id":"3","type":"generation.failed","resource_id":"s1","sequence":3,"timestamp":"2026-09-17T00:00:02Z","schema_version":1,"data":{"code":"agent_unavailable","stop_reason":"failed"}}',
  "id: 3",
  "",
  "",
].join("\n")

describe("streamSessionEvents", () => {
  it("parses typed events, ignores keep-alive comments and resumes from a cursor", async () => {
    const fetchImpl = vi.fn(async () => sseResponse(STREAM))
    const client = new ApiClient({
      baseUrl: "https://api.test",
      getAccessToken: () => "token-1",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    const seen: string[] = []
    for await (const event of streamSessionEvents(client, SESSION_ID, {
      lastEventId: 41,
    })) {
      seen.push(event.type)
    }

    expect(seen).toEqual([
      "generation.started",
      "message.delta",
      "generation.failed",
    ])
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe(
      `https://api.test/v1/sessions/${SESSION_ID}/events?last_event_id=41`,
    )
    expect((init.headers as Record<string, string>).Accept).toBe("text/event-stream")
  })

  it("exposes the event payload and sequence", async () => {
    const fetchImpl = vi.fn(async () => sseResponse(STREAM))
    const client = new ApiClient({
      baseUrl: "https://api.test",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    const events = []
    for await (const event of streamSessionEvents(client, SESSION_ID)) {
      events.push(event)
    }

    expect(events[0].sequence).toBe(1)
    expect(events[0].data.model).toBe("gpt-x")
    expect(events[2].data.code).toBe("agent_unavailable")
    expect(events[2].data.stop_reason).toBe("failed")
  })

  it("turns an unavailable stream into a typed error", async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify({ code: "session_not_found", message: "会话不存在" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    )
    const client = new ApiClient({
      baseUrl: "https://api.test",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    })

    const failure = await (async () => {
      for await (const _event of streamSessionEvents(client, SESSION_ID)) {
        // no events expected
      }
    })().catch((error) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect((failure as ApiError).code).toBe("session_not_found")
  })
})

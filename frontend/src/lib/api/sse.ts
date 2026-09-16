import { createParser, type EventSourceMessage } from "eventsource-parser"

import type { ApiClient } from "./client"
import { ApiError } from "./errors"
import type { SessionEvent, SessionEventType, Uuid } from "./types"

export interface SessionEventStreamOptions {
  /** Resume after this event sequence; the backend replays what was missed. */
  lastEventId?: number | string | null
  signal?: AbortSignal
  /** Invoked for every parsed event, before it is yielded. */
  onEvent?: (event: SessionEvent) => void
}

/**
 * Subscribe to a session's SSE stream.
 *
 * Uses `fetch` instead of `EventSource` because the API needs an Authorization
 * header and an event cursor; the backend closes idle streams, so callers should
 * reconnect with the last seen sequence number.
 */
export async function* streamSessionEvents(
  client: ApiClient,
  sessionId: Uuid,
  options: SessionEventStreamOptions = {},
): AsyncGenerator<SessionEvent, void, void> {
  const query: Record<string, string | number> = {}
  if (options.lastEventId !== undefined && options.lastEventId !== null) {
    query.last_event_id = String(options.lastEventId)
  }
  const response = await client.raw(`/v1/sessions/${sessionId}/events`, {
    headers: { Accept: "text/event-stream" },
    query,
    signal: options.signal,
  })

  if (!response.ok) {
    const text = await response.text()
    try {
      throw new ApiError(response.status, JSON.parse(text))
    } catch (error) {
      if (error instanceof ApiError) {
        throw error
      }
      throw new ApiError(response.status, { message: response.statusText })
    }
  }
  if (!response.body) {
    throw new ApiError(response.status, {
      code: "stream_unavailable",
      message: "服务端没有返回事件流",
    })
  }

  const queue: SessionEvent[] = []
  let notify: (() => void) | null = null
  const parser = createParser({
    onEvent: (message: EventSourceMessage) => {
      const event = toSessionEvent(message)
      if (!event) {
        return
      }
      options.onEvent?.(event)
      queue.push(event)
      notify?.()
    },
  })

  const reader = response.body
    .pipeThrough(new TextDecoderStream())
    .getReader()

  try {
    while (true) {
      while (queue.length > 0) {
        yield queue.shift() as SessionEvent
      }
      const { done, value } = await reader.read()
      if (done) {
        return
      }
      parser.feed(value)
    }
  } finally {
    reader.cancel().catch(() => undefined)
    notify = null
  }
}

function toSessionEvent(message: EventSourceMessage): SessionEvent | null {
  if (!message.event || message.event === "message") {
    return null
  }
  let data: Record<string, unknown> = {}
  if (message.data) {
    try {
      data = JSON.parse(message.data)
    } catch {
      return null
    }
  }
  if (message.id) {
    data.sequence = data.sequence ?? Number(message.id)
  }
  return {
    event_id: String(data.event_id ?? message.id ?? ""),
    type: message.event as SessionEventType,
    resource_id: String(data.resource_id ?? ""),
    sequence: Number(data.sequence ?? 0),
    timestamp: String(data.timestamp ?? ""),
    schema_version: Number(data.schema_version ?? 1),
    data: (data.data as Record<string, unknown>) ?? {},
  }
}

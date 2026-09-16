import { useEffect, useRef, useState } from "react"

import type { SessionEvent } from "@/lib/api"
import { streamSessionEvents } from "@/lib/api/sse"
import { useApi } from "@/lib/api/provider"

const RECONNECT_DELAY_MS = 600

/**
 * Subscribe to a session's event stream.
 *
 * The backend closes idle streams, so this hook reconnects with the last seen
 * sequence and lets the server replay what was missed. Generation and the SSE
 * subscription are decoupled: closing the page does not stop a running turn.
 */
export function useSessionEvents(
  sessionId: string | null,
  onEvent: (event: SessionEvent) => void,
) {
  const { api } = useApi()
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent
  const cursorRef = useRef(0)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!sessionId) {
      return
    }
    cursorRef.current = 0
    const controller = new AbortController()
    let stopped = false

    async function run() {
      while (!stopped) {
        try {
          const stream = streamSessionEvents(api.client, sessionId as string, {
            lastEventId: cursorRef.current || undefined,
            signal: controller.signal,
          })
          for await (const event of stream) {
            if (stopped) {
              return
            }
            cursorRef.current = Math.max(cursorRef.current, event.sequence)
            setConnected(true)
            handlerRef.current(event)
          }
          setConnected(false)
        } catch {
          if (stopped) {
            return
          }
          setConnected(false)
        }
        if (stopped) {
          return
        }
        await new Promise((resolve) => setTimeout(resolve, RECONNECT_DELAY_MS))
      }
    }

    void run()
    return () => {
      stopped = true
      controller.abort()
      setConnected(false)
    }
  }, [api, sessionId])

  return { connected, lastSequence: cursorRef }
}

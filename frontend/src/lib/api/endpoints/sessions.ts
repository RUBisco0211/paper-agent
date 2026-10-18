import type { ApiClient } from "../client"
import type {
  Citation,
  LlmCatalog,
  LlmConfigInput,
  MessageAccepted,
  MessageInput,
  Page,
  ResumeResponse,
  Session,
  SessionDetail,
  SessionEntry,
  Uuid,
} from "@/types/business"

const SESSIONS = "/v1/sessions"

import type { SessionListParams } from "@/types/session"

export function sessionEndpoints(client: ApiClient) {
  return {
    llmCatalog: () => client.request<LlmCatalog>("/v1/llm-catalog"),

    /** 范围三选一：全局（都不传）、项目、单篇文献。 */
    create: (
      input: { title?: string; project_id?: Uuid; paper_id?: Uuid } = {},
    ) => client.request<Session>(SESSIONS, { method: "POST", json: input }),

    list: (params: SessionListParams = {}) =>
      client.request<Page<Session>>(SESSIONS, { query: { ...params } }),

    /** Includes the pending snapshot and its FIFO order. */
    detail: (sessionId: Uuid) =>
      client.request<SessionDetail>(`${SESSIONS}/${sessionId}`),

    rename: (sessionId: Uuid, title: string) =>
      client.request<Session>(`${SESSIONS}/${sessionId}`, {
        method: "PATCH",
        json: { title },
      }),

    remove: (sessionId: Uuid) =>
      client.request<void>(`${SESSIONS}/${sessionId}`, { method: "DELETE" }),

    /** History replay; the cursor is the last seen entry sequence. */
    entries: (
      sessionId: Uuid,
      params: { after_sequence?: number; limit?: number } = {},
    ) =>
      client.request<Page<SessionEntry>>(`${SESSIONS}/${sessionId}/entries`, {
        query: { ...params },
      }),

    /** Submit input; a busy session queues it instead of starting another turn. */
    sendMessage: (sessionId: Uuid, input: MessageInput) =>
      client.request<MessageAccepted>(`${SESSIONS}/${sessionId}/messages`, {
        method: "POST",
        json: input,
      }),

    stop: (sessionId: Uuid) =>
      client.request<{ stopped: boolean }>(`${SESSIONS}/${sessionId}/stop`, {
        method: "POST",
      }),

    /** Resume queued input after a stop, failure or backend restart. */
    resume: (sessionId: Uuid, llmConfig: LlmConfigInput) =>
      client.request<ResumeResponse>(`${SESSIONS}/${sessionId}/resume`, {
        method: "POST",
        json: { llm_config: llmConfig },
      }),

    citation: (sessionId: Uuid, citationId: string) =>
      client.request<Citation>(
        `${SESSIONS}/${sessionId}/citations/${citationId}`,
      ),
  }
}

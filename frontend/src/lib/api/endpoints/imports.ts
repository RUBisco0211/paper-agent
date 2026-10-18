import type { ApiClient } from "../client"
import type { ExternalDiscoveryResponse, ImportQueueItem, Page, PaperImport, SearchInput, SearchResponse, Uuid } from "@/types/business"

export function importEndpoints(client: ApiClient) {
  return {
    /** Accepts a DOI, an arXiv id or their canonical links. */
    start: (identifier: string, options: { project_id?: Uuid } = {}) =>
      client.request<PaperImport>("/v1/imports", {
        method: "POST",
        json: { identifier, ...options },
      }),

    /** Poll until the status is terminal (ready / pdf_unavailable / failed). */
    status: (importId: Uuid) => client.request<PaperImport>(`/v1/imports/${importId}`),

    list: (params: { limit?: number } = {}) =>
      client.request<Page<PaperImport>>("/v1/imports", { query: { ...params } }),
    queue: () => client.request<{ items: ImportQueueItem[] }>("/v1/imports/queue"),
    approve: (sessionId: Uuid, candidateTokens: string[]) =>
      client.request<{ id: Uuid; count: number }>("/v1/imports/approvals", {
        method: "POST", json: { session_id: sessionId, candidate_tokens: candidateTokens },
      }),
  }
}

export function retrievalEndpoints(client: ApiClient) {
  return {
    discover: (query: string, limit = 10) =>
      client.request<ExternalDiscoveryResponse>("/v1/discover-papers", {
        method: "POST", json: { query, limit },
      }),
    search: (input: SearchInput) =>
      client.request<SearchResponse>("/v1/search", {
        method: "POST",
        json: input,
      }),
  }
}

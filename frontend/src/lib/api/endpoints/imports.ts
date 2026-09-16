import type { ApiClient } from "../client"
import type { Page, PaperImport, SearchInput, SearchResponse, Uuid } from "../types"

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
  }
}

export function retrievalEndpoints(client: ApiClient) {
  return {
    search: (input: SearchInput) =>
      client.request<SearchResponse>("/v1/search", {
        method: "POST",
        json: input,
      }),
  }
}

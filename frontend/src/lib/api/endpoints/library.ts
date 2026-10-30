import type { ApiClient } from "../client"
import { ApiError } from "../errors"
import type {
  Page,
  PaperListParams,
  PaperMarkdownResponse,
  PaperBlocksResponse,
  PaperBlock,
  UploadResponse,
  UserPaperDetail,
  UserPaperSummary,
  Uuid,
} from "@/types/business"

const PAPERS = "/v1/papers"

export function libraryEndpoints(client: ApiClient) {
  return {
    /** Upload a local PDF; the paper joins its run and appears once it is usable. */
    upload: (
      file: File,
      options: { signal?: AbortSignal; projectId?: Uuid } = {},
    ) => {
      const form = new FormData()
      form.append("file", file)
      if (options.projectId) form.append("project_id", options.projectId)
      return client.request<UploadResponse>(PAPERS, {
        method: "POST",
        body: form,
        signal: options.signal,
      })
    },

    list: (params: PaperListParams = {}) =>
      client.request<Page<UserPaperSummary>>(PAPERS, { query: { ...params } }),

    detail: (paperId: Uuid) =>
      client.request<UserPaperDetail>(`${PAPERS}/${paperId}`),

    blocks: (paperId: Uuid, params: { type?: string; offset?: number; limit?: number } = {}) =>
      client.request<PaperBlocksResponse>(`${PAPERS}/${paperId}/blocks`, { query: params }),

    block: (paperId: Uuid, blockId: number) =>
      client.request<PaperBlock>(`${PAPERS}/${paperId}/blocks/${blockId}`),

    /** The parsed full text as one markdown document; images stay relative. */
    markdown: (paperId: Uuid) =>
      client.request<PaperMarkdownResponse>(`${PAPERS}/${paperId}/markdown`),

    /** Fetched as a blob: markdown images need the access token too. */
    assetBlob: async (paperId: Uuid, path: string, options: { signal?: AbortSignal } = {}) => {
      const response = await client.raw(`${PAPERS}/${paperId}/assets/${path}`, options)
      if (!response.ok) throw await toError(response)
      return response.blob()
    },

    blockImageBlob: async (paperId: Uuid, blockId: number, options: { signal?: AbortSignal } = {}) => {
      const response = await client.raw(`${PAPERS}/${paperId}/blocks/${blockId}/image`, options)
      if (!response.ok) throw await toError(response)
      return response.blob()
    },

    /** Fetched as a blob so the caller can render it in an embedded viewer. */
    pdfBlob: async (paperId: Uuid, options: { signal?: AbortSignal } = {}) => {
      const response = await client.raw(`${PAPERS}/${paperId}/pdf`, {
        signal: options.signal,
      })
      if (!response.ok) {
        throw await toError(response)
      }
      return response.blob()
    },

    pdfUrl: (paperId: Uuid) => `${client.base}${PAPERS}/${paperId}/pdf`,

    assetUrl: (paperId: Uuid, path: string) =>
      `${client.base}${PAPERS}/${paperId}/assets/${path}`,

  }
}

async function toError(response: Response): Promise<ApiError> {
  const text = await response.text()
  try {
    return new ApiError(response.status, JSON.parse(text))
  } catch {
    return new ApiError(response.status, { message: response.statusText })
  }
}

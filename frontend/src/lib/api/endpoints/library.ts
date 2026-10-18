import type { ApiClient } from "../client"
import { ApiError } from "../errors"
import type {
  FetchPdfResponse,
  IngestionJob,
  FetchMetadataResponse,
  Page,
  PaperInfoInput,
  PaperListParams,
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
    /** Upload a local PDF; the response already contains the library entry. */
    upload: (file: File, options: { signal?: AbortSignal } = {}) => {
      const form = new FormData()
      form.append("file", file)
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

    /** Attach or replace the full text of an existing entry. */
    attachPdf: (paperId: Uuid, file: File) => {
      const form = new FormData()
      form.append("file", file)
      return client.request<UploadResponse>(`${PAPERS}/${paperId}/pdf`, {
        method: "POST",
        body: form,
      })
    },

    /** Re-attempt the download announced by the paper's identifier. */
    fetchPdf: (paperId: Uuid) =>
      client.request<FetchPdfResponse>(`${PAPERS}/${paperId}/fetch-pdf`, {
        method: "POST",
      }),

    /** 编辑条目书目信息（界面「编辑信息」）。 */
    updateInfo: (paperId: Uuid, input: PaperInfoInput) =>
      client.request<UserPaperDetail>(`${PAPERS}/${paperId}/info`, {
        method: "PATCH",
        json: input,
      }),

    /** 按条目标识符在线获取元数据（界面「获取元数据」）。 */
    fetchMetadata: (paperId: Uuid) =>
      client.request<FetchMetadataResponse>(
        `${PAPERS}/${paperId}/fetch-metadata`,
        { method: "POST" },
      ),

    ingestionJob: (jobId: Uuid) =>
      client.request<IngestionJob>(`/v1/ingestion-jobs/${jobId}`),

    retryIngestionJob: (jobId: Uuid) =>
      client.request<IngestionJob>(`/v1/ingestion-jobs/${jobId}/retry`, {
        method: "POST",
      }),
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

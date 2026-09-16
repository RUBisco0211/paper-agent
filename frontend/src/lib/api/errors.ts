import type { ApiErrorBody } from "./types"

/** Every non-2xx response is surfaced as one typed error. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly details: unknown

  constructor(status: number, body: Partial<ApiErrorBody> = {}) {
    super(body.message ?? `请求失败（HTTP ${status}）`)
    this.name = "ApiError"
    this.status = status
    this.code = body.code ?? "unknown_error"
    this.requestId = body.request_id ?? null
    this.details = body.details ?? null
  }

  /** 401 means the caller must (re)authenticate rather than retry blindly. */
  get isUnauthorized(): boolean {
    return this.status === 401
  }

  /** Input problems are shown next to the form; everything else is a banner. */
  get isValidation(): boolean {
    return this.status === 422 || this.status === 415 || this.status === 413
  }

  get isNotAllowed(): boolean {
    return this.status === 403 || this.status === 404
  }

  /** Upstream providers and still-processing resources. */
  get isUnavailable(): boolean {
    return this.status === 429 || this.status === 502 || this.status === 503 || this.status === 504
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

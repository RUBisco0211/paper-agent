import { ApiError } from "./errors"
import type { AccessToken, AuthSession, ApiErrorBody } from "./types"

export type AccessTokenSink = (session: AccessToken | null) => void

export interface ApiClientOptions {
  /**
   * Backend origin. Defaults to `VITE_API_BASE_URL`, or the same origin so the
   * Vite dev proxy can handle `/v1`.
   */
  baseUrl?: string
  /** AgentScope origin; used when both backends share one access token. */
  agentServiceBaseUrl?: string
  /** Reads the in-memory access token; the token itself is never persisted. */
  getAccessToken?: () => string | null
  /** Called whenever tokens are issued, refreshed or cleared. */
  onAccessToken?: AccessTokenSink
  /** Injection point for tests. */
  fetchImpl?: typeof fetch
  /** Refresh through the business API when this client targets AgentScope. */
  refreshAccessToken?: () => Promise<AccessToken>
  /** AgentScope requests do not need the business refresh cookie. */
  credentials?: RequestCredentials
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE"
  /** JSON body; use `body` for raw payloads (for example uploads). */
  json?: unknown
  body?: BodyInit
  query?: Record<string, string | number | boolean | undefined | null>
  headers?: Record<string, string>
  signal?: AbortSignal
  /** Skip the automatic refresh-and-retry on 401. */
  skipRefresh?: boolean
  /** Upload progress reporting (fetch only reports upload for streams). */
  credentials?: RequestCredentials
}

const REFRESH_PATH = "/v1/auth/refresh"
/** A failed login or register must not trigger a token rotation attempt. */
const SESSION_ESTABLISHING_PATHS = ["/v1/auth/login", "/v1/auth/register"]

export class ApiClient {
  private readonly baseUrl: string
  private readonly fetchImpl: typeof fetch
  private readonly getAccessToken: () => string | null
  private readonly onAccessToken: AccessTokenSink
  private readonly refreshAccessToken?: () => Promise<AccessToken>
  private readonly defaultCredentials: RequestCredentials
  private refreshPromise: Promise<AccessToken> | null = null

  constructor(options: ApiClientOptions = {}) {
    const configured = options.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? ""
    this.baseUrl = configured.replace(/\/$/, "")
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis)
    this.getAccessToken = options.getAccessToken ?? (() => null)
    this.onAccessToken = options.onAccessToken ?? (() => {})
    this.refreshAccessToken = options.refreshAccessToken
    this.defaultCredentials = options.credentials ?? "include"
  }

  get base(): string {
    return this.baseUrl
  }

  /** Perform one request and normalize failures into an `ApiError`. */
  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const response = await this.send(path, options)
    if (response.status === 401 && !options.skipRefresh && this.shouldRefresh(path)) {
      await this.refresh()
      const retried = await this.send(path, { ...options, skipRefresh: true })
      return this.parse<T>(retried)
    }
    return this.parse<T>(response)
  }

  /** Raw response access, used by streaming and file downloads. */
  async raw(path: string, options: RequestOptions = {}): Promise<Response> {
    const response = await this.send(path, options)
    if (response.status === 401 && !options.skipRefresh && this.shouldRefresh(path)) {
      await this.refresh()
      return this.send(path, { ...options, skipRefresh: true })
    }
    return response
  }

  /**
   * Rotate the refresh cookie exactly once, even when many requests fail at the
   * same time: the backend revokes the whole token family on replay.
   */
  async refresh(): Promise<AccessToken> {
    if (this.refreshAccessToken) {
      return this.refreshAccessToken()
    }
    if (!this.refreshPromise) {
      this.refreshPromise = this.performRefresh().finally(() => {
        this.refreshPromise = null
      })
    }
    return this.refreshPromise
  }

  clearSession(): void {
    this.onAccessToken(null)
  }

  private shouldRefresh(path: string): boolean {
    if (path.startsWith(REFRESH_PATH)) {
      return false
    }
    return !SESSION_ESTABLISHING_PATHS.some((prefix) => path.startsWith(prefix))
  }

  private async performRefresh(): Promise<AccessToken> {
    const response = await this.fetchImpl(this.url(REFRESH_PATH), {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    })
    const session = await this.parse<AccessToken>(response)
    this.onAccessToken(session)
    return session
  }

  private async send(path: string, options: RequestOptions): Promise<Response> {
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...options.headers,
    }
    const token = this.getAccessToken()
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }
    let body = options.body
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json"
      body = JSON.stringify(options.json)
    }
    return this.fetchImpl(this.url(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body,
      signal: options.signal,
      credentials: options.credentials ?? this.defaultCredentials,
    })
  }

  private async parse<T>(response: Response): Promise<T> {
    if (response.status === 204) {
      return undefined as T
    }
    const text = await response.text()
    const payload = text ? safeJson(text) : undefined
    if (!response.ok) {
      throw new ApiError(
        response.status,
        (payload as Partial<ApiErrorBody>) ?? {
          code: "unknown_error",
          message: response.statusText,
        },
      )
    }
    return payload as T
  }

  private url(
    path: string,
    query?: Record<string, string | number | boolean | undefined | null>,
  ): string {
    const target = `${this.baseUrl}${path}`
    if (!query) {
      return target
    }
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        params.append(key, String(value))
      }
    }
    const suffix = params.toString()
    return suffix ? `${target}?${suffix}` : target
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

/** The auth endpoints are thin wrappers around the generic client. */
export function authEndpoints(client: ApiClient) {
  return {
    register: (input: { email: string; password: string; display_name?: string }) =>
      client.request<AuthSession>("/v1/auth/register", {
        method: "POST",
        json: input,
        skipRefresh: true,
      }),
    login: (input: { email: string; password: string }) =>
      client.request<AuthSession>("/v1/auth/login", {
        method: "POST",
        json: input,
        skipRefresh: true,
      }),
    refresh: () => client.refresh(),
    logout: () =>
      client.request<void>("/v1/auth/logout", { method: "POST", skipRefresh: true }),
    me: () => client.request<import("./types").User>("/v1/auth/me"),
    setTimezone: (timezone: string) =>
      client.request<{ timezone: string }>("/v1/auth/timezone", {
        method: "PATCH",
        json: { timezone },
      }),
  }
}

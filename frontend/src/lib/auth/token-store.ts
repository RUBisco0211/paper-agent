import type { AccessToken, ApiClientOptions } from "@/lib/api"

/**
 * The access token lives in memory only.
 *
 * The refresh token stays in an HttpOnly cookie owned by the backend, so a hard
 * reload restores the session by calling refresh instead of reading storage.
 */
export class AccessTokenStore {
  private session: AccessToken | null = null
  private readonly listeners = new Set<(session: AccessToken | null) => void>()

  get current(): AccessToken | null {
    return this.session
  }

  /** True when the access token is missing or about to expire. */
  get needsRefresh(): boolean {
    if (!this.session) {
      return true
    }
    return new Date(this.session.expires_at).getTime() - 30_000 <= Date.now()
  }

  set(session: AccessToken | null): void {
    this.session = session
    for (const listener of this.listeners) {
      listener(session)
    }
  }

  clear(): void {
    this.set(null)
  }

  subscribe(listener: (session: AccessToken | null) => void): () => void {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  /** Wire this store into `createApi({...store.clientOptions})`. */
  get clientOptions(): Pick<
    ApiClientOptions,
    "getAccessToken" | "onAccessToken"
  > {
    return {
      getAccessToken: () => this.session?.access_token ?? null,
      onAccessToken: (session) => this.set(session),
    }
  }
}

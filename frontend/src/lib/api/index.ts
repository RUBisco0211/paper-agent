import { ApiClient, authEndpoints, type ApiClientOptions } from "./client"
import { libraryEndpoints } from "./endpoints/library"
import { projectEndpoints } from "./endpoints/projects"
import { sessionEndpoints } from "./endpoints/sessions"
import { importEndpoints, retrievalEndpoints } from "./endpoints/imports"

export * from "./client"
export * from "./errors"
export * from "./sse"
export type * from "./types"

/**
 * One object per backend domain, sharing a single client so token refresh stays
 * single-flight across the whole app.
 */
export function createApi(options: ApiClientOptions = {}) {
  const client = new ApiClient(options)
  return {
    client,
    auth: authEndpoints(client),
    library: libraryEndpoints(client),
    projects: projectEndpoints(client),
    sessions: sessionEndpoints(client),
    imports: importEndpoints(client),
    retrieval: retrievalEndpoints(client),
  }
}

export type Api = ReturnType<typeof createApi>

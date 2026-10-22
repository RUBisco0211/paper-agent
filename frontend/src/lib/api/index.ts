import { ApiClient, authEndpoints, type ApiClientOptions } from "./client"
import { libraryEndpoints } from "./endpoints/library"
import { projectEndpoints } from "./endpoints/projects"
import { sessionEndpoints } from "./endpoints/sessions"
import { importEndpoints, retrievalEndpoints } from "./endpoints/imports"
import { serviceCredentialEndpoints } from "./endpoints/serviceCredentials"

export * from "./client"
export * from "./errors"
export type * from "@/types/business"

/**
 * One object per backend domain, sharing a single client so token refresh stays
 * single-flight across the whole app.
 */
export function createApi(options: ApiClientOptions = {}) {
  const client = new ApiClient(options)
  const agentService = new ApiClient({
    ...options,
    baseUrl:
      options.agentServiceBaseUrl ??
      import.meta.env.VITE_AGENT_SERVICE_BASE_URL ??
      "http://127.0.0.1:8001",
    credentials: "omit",
    refreshAccessToken: () => client.refresh(),
  })
  return {
    client,
    agentService,
    auth: authEndpoints(client),
    library: libraryEndpoints(client),
    projects: projectEndpoints(client),
    sessions: sessionEndpoints(client),
    imports: importEndpoints(client),
    retrieval: retrievalEndpoints(client),
    serviceCredentials: serviceCredentialEndpoints(client),
  }
}

export type Api = ReturnType<typeof createApi>

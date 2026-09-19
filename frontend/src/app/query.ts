import { QueryClient } from "@tanstack/react-query"

/**
 * Shared cache policy.
 *
 * Ingestion is polled while a paper is still processing, so the default is a
 * short stale window plus refetch-on-window-focus instead of aggressive
 * background polling everywhere.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        retry: (failureCount, error) => {
          const status = (error as { status?: number }).status
          if (status && status >= 400 && status < 500) {
            return false
          }
          return failureCount < 2
        },
        refetchOnWindowFocus: true,
      },
      mutations: { retry: false },
    },
  })
}

export const queryKeys = {
  llmCatalog: ["llm-catalog"] as const,
  papers: (params?: unknown) => ["papers", params ?? {}] as const,
  paper: (paperId: string) => ["paper", paperId] as const,
  ingestionJob: (jobId: string) => ["ingestion-job", jobId] as const,
  projects: (params?: unknown) => ["projects", params ?? {}] as const,
  project: (projectId: string) => ["project", projectId] as const,
  projectPapers: (projectId: string, params?: unknown) =>
    ["project-papers", projectId, params ?? {}] as const,
  sessions: (params?: unknown) => ["sessions", params ?? {}] as const,
  session: (sessionId: string) => ["session", sessionId] as const,
  entries: (sessionId: string) => ["session-entries", sessionId] as const,
  importJob: (importId: string) => ["import", importId] as const,
  search: (params: unknown) => ["search", params] as const,
}

import type { ApiClient } from "../client";
import type {
  AddProjectPapersResponse,
  Page,
  Project,
  UserPaperSummary,
  Uuid,
} from "../types";

const PROJECTS = "/v1/projects";

export function projectEndpoints(client: ApiClient) {
  return {
    create: (input: { name: string; description?: string }) =>
      client.request<Project>(PROJECTS, { method: "POST", json: input }),

    list: (params: { limit?: number; offset?: number } = {}) =>
      client.request<Page<Project>>(PROJECTS, { query: { ...params } }),

    detail: (projectId: Uuid) =>
      client.request<Project>(`${PROJECTS}/${projectId}`),

    rename: (
      projectId: Uuid,
      input: { name?: string; description?: string | null },
    ) =>
      client.request<Project>(`${PROJECTS}/${projectId}`, {
        method: "PATCH",
        json: input,
      }),

    /** Deleting a project keeps the personal library entries and its sessions. */
    remove: (projectId: Uuid) =>
      client.request<void>(`${PROJECTS}/${projectId}`, { method: "DELETE" }),

    papers: (
      projectId: Uuid,
      params: { limit?: number; offset?: number; q?: string } = {},
    ) =>
      client.request<Page<UserPaperSummary>>(
        `${PROJECTS}/${projectId}/papers`,
        {
          query: { ...params },
        },
      ),

    addPapers: (projectId: Uuid, paperIds: Uuid[]) =>
      client.request<AddProjectPapersResponse>(
        `${PROJECTS}/${projectId}/papers`,
        { method: "POST", json: { paper_ids: paperIds } },
      ),
  };
}

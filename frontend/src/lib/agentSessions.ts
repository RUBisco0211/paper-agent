import type { Api, Page } from "@/lib/api"
import { agentApi } from "@/lib/api/agentscope/agent"
import { credentialApi } from "@/lib/api/agentscope/credential"
import { sessionApi } from "@/lib/api/agentscope/session"
import type { ChatModelConfig } from "@/types/agent"
import type { BoundSession, SessionBinding } from "@/types/session"
import { ApiError as AgentApiError } from "@/lib/api/agentscope/client"

const BINDINGS = "/v1/session-bindings"

export function sameSessionId(left: string, right: string): boolean {
  return left.replaceAll("-", "").toLowerCase() === right.replaceAll("-", "").toLowerCase()
}

export async function listBindings(api: Api): Promise<SessionBinding[]> {
  const items: SessionBinding[] = []
  let total = 0
  do {
    const page = await api.client.request<Page<SessionBinding>>(BINDINGS, {
      query: { limit: 100, offset: items.length },
    })
    items.push(...page.items)
    total = page.total
    if (page.items.length === 0) break
  } while (items.length < total)
  return items
}

export async function listBoundSessions(api: Api): Promise<BoundSession[]> {
  const [agents, bindings] = await Promise.all([agentApi.list(), listBindings(api)])
  const byId = new Map(bindings.map((item) => [item.session_id.replaceAll("-", "").toLowerCase(), item]))
  const groups = await Promise.all(
    agents.agents.map(async (agent) => {
      const result = await sessionApi.list(agent.id)
      return result.sessions.flatMap((session) => {
        const binding = byId.get(session.session.id.replaceAll("-", "").toLowerCase())
        return binding ? [{ agentId: agent.id, session, binding }] : []
      })
    }),
  )
  return groups.flat().sort((a, b) =>
    b.session.session.created_at.localeCompare(a.session.session.created_at),
  )
}

export async function availableChatModels(api: Api): Promise<ChatModelConfig[]> {
  const [catalog, credentials] = await Promise.all([
    api.sessions.llmCatalog(),
    credentialApi.list(),
  ])
  return catalog.providers.flatMap((provider) =>
    credentials.credentials
      .filter((credential) => credential.data.type === `${provider.id}_credential`)
      .flatMap((credential) =>
        provider.models.map((model) => ({
          type: `${provider.id}_credential`,
          credential_id: credential.id,
          model: model.id,
          parameters: {},
        })),
      ),
  )
}

export async function createBoundSession(
  api: Api,
  input: { projectId?: string; modelConfig?: ChatModelConfig } = {},
): Promise<{ agentId: string; sessionId: string }> {
  const models = input.modelConfig ? [input.modelConfig] : await availableChatModels(api)
  if (models.length === 0) throw new Error("请先在模型设置中保存凭据")
  const listed = await agentApi.list()
  const agentId = listed.agents[0]?.id ?? (await agentApi.create({ name: "文献助手" })).agent_id
  const created = await sessionApi.create({ agent_id: agentId, chat_model_config: models[0] })
  try {
    await api.client.request(BINDINGS, {
      method: "POST",
      json: {
        session_id: created.session_id,
        ...(input.projectId ? { project_id: input.projectId } : {}),
      },
    })
  } catch (bindingError) {
    try {
      await sessionApi.delete(created.session_id, agentId)
    } catch (cleanupError) {
      throw new AggregateError([bindingError, cleanupError], "创建会话失败")
    }
    throw bindingError
  }
  return { agentId, sessionId: created.session_id }
}

export async function deleteBoundSession(
  api: Api,
  input: { agentId: string; sessionId: string },
): Promise<void> {
  try {
    await sessionApi.delete(input.sessionId, input.agentId)
  } catch (cause) {
    if (!(cause instanceof AgentApiError && cause.status === 404)) throw cause
  }
  await api.client.request(`${BINDINGS}/${input.sessionId}`, { method: "DELETE" })
}

export async function deleteProjectWithSessions(api: Api, projectId: string): Promise<void> {
  const bindings = (await listBindings(api)).filter((item) => item.project_id === projectId)
  if (bindings.length) {
    const sessions = await listBoundSessions(api)
    for (const binding of bindings) {
      const active = sessions.find((item) => sameSessionId(item.binding.session_id, binding.session_id))
      if (active) {
        await deleteBoundSession(api, { agentId: active.agentId, sessionId: active.session.session.id })
      } else {
        await api.client.request(`${BINDINGS}/${binding.session_id}`, { method: "DELETE" })
      }
    }
  }
  await api.projects.remove(projectId)
}

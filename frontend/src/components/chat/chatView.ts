export interface ChatSessionSummary {
  agentId: string
  session: { session: { id: string; created_at: string; updated_at?: string } }
}

export function mostRecentSession<T extends ChatSessionSummary>(sessions: T[]): T | null {
  return sessions.reduce<T | null>((latest, item) =>
    !latest || (item.session.session.updated_at ?? item.session.session.created_at) >
      (latest.session.session.updated_at ?? latest.session.session.created_at) ? item : latest, null)
}

export function chatPath(session: ChatSessionSummary | null): string {
  return session ? `/chat/${session.agentId}/${session.session.session.id}` : "/chat"
}

export function reasoningEffortsForModel(
  providers: Array<{ id: string; models: Array<{ id: string; reasoning_efforts: string[] }> }>,
  credentialType: string,
  modelId: string,
): string[] {
  const provider = providers.find((item) => `${item.id}_credential` === credentialType)
  return provider?.models.find((item) => item.id === modelId)?.reasoning_efforts ?? []
}

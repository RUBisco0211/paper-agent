import type { SessionView } from "./agent"
import type { SessionScope, Uuid } from "./business"

export interface SessionBinding {
  session_id: string
  project_id: string | null
  scope: "library" | "project"
}

export interface BoundSession {
  agentId: string
  session: SessionView
  binding: SessionBinding
}

export interface SessionListParams {
  limit?: number
  offset?: number
  scope?: SessionScope
  project_id?: Uuid
  paper_id?: Uuid
}

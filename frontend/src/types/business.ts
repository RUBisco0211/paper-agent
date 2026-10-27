/**
 * Shared API types, mirroring the backend Pydantic schemas.
 *
 * Keep these in sync with the backend schemas (backend/app/<domain>/schemas.py):
 * the backend is the source of truth, and a field is optional here only when the
 * API may omit it.
 */

export type Uuid = string

export interface ExternalPaperCandidate {
  source_id: string
  title: string
  doi?: string | null
  pdf_url?: string | null
  url?: string | null
  year?: number | null
  authors?: string[]
  sources?: string[]
}

export interface ExternalDiscoveryResponse {
  papers: ExternalPaperCandidate[]
  failed_sources: string[]
}

// --- Common ---------------------------------------------------------------
export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface ApiErrorBody {
  code: string
  message: string
  request_id?: string | null
  details?: unknown
}

// --- Auth -----------------------------------------------------------------
export interface User {
  id: Uuid
  email: string
  display_name: string
  created_at: string
}

export interface AccessToken {
  access_token: string
  token_type: "bearer"
  expires_in: number
  expires_at: string
}

export interface AuthSession extends AccessToken {
  user: User
}

export type EmailCodePurpose = "register" | "password_reset"

export interface EmailCodeChallenge {
  challenge_id: string
  retry_after: number
  expires_in: number
}

export interface EmailVerification {
  verification_token: string
  expires_in: number
}

export interface PasswordVerificationInput {
  verification_token: string
  password: string
  password_confirmation: string
}

export interface RegisterInput extends PasswordVerificationInput {
  display_name?: string
}

export interface LoginInput {
  email: string
  password: string
}

// --- Library --------------------------------------------------------------
export type MetadataStatus =
  | "recognized"
  | "partial"
  | "unrecognized"
  | "provider_failed"
  | "user_provided"

export interface Capabilities {
  has_source: boolean
  has_metadata: boolean
  has_parsed: boolean
  has_index: boolean
  has_embedding: boolean
}

export type RunStage = "parse" | "chunk" | "embed"
export type RunStatus = "pending" | "running" | "success" | "failed"
export type DownloadStatus = "pending" | "running" | "success" | "failed"

export interface UserPaperSummary {
  id: Uuid
  title: string | null
  authors: string[]
  year?: number | null
  venue?: string | null
  doi?: string | null
  arxiv_id?: string | null
  added_at: string
  /** Projects this entry belongs to; empty when it is only in the library. */
  project_ids?: Uuid[]
  capabilities: Capabilities
  run_status?: RunStatus | null
}

export interface UserPaperDetail extends UserPaperSummary {
  abstract?: string | null
  metadata?: Record<string, unknown> | null
  metadata_sources?: Array<Record<string, unknown>> | null
  pdf: {
    available: boolean
    page_count?: number | null
    byte_size?: number | null
  }
  pdf_version?: string | null
  artifact_version?: string | null
}

export interface PaperBlock {
  id: number
  type: string
  page: number
  text: string
  formula?: string | null
  has_image?: boolean
  bbox: number[] | null
  page_size: number[] | null
  coordinate_system: "normalized" | "page" | null
}

export interface PaperBlocksResponse {
  types: string[]
  items: PaperBlock[]
  total: number
  offset: number
  limit: number
}

export interface UploadResponse {
  run_id: Uuid
  status: RunStatus
}

export interface MetadataFetchResult {
  status: MetadataStatus
  source?: string | null
  error_code?: string | null
  applied_fields: string[]
}

export interface PaperListParams {
  limit?: number
  offset?: number
  q?: string
}

// --- Projects -------------------------------------------------------------
export interface Project {
  id: Uuid
  name: string
  description?: string | null
  paper_count: number
  created_at: string
  updated_at: string
}

export interface AddProjectPapersResponse {
  added: UserPaperSummary[]
  already_present: Uuid[]
}

// --- Sessions -------------------------------------------------------------
/** 界面用词：library = 全局，project = 项目，paper = 单篇文献 */
export type SessionScope = "library" | "project" | "paper"
export type Delivery = "steering" | "follow_up"

export interface PendingCounts {
  steering: number
  follow_up: number
}

export interface Session {
  id: Uuid
  title: string | null
  scope: SessionScope
  project_id?: Uuid | null
  paper_id?: Uuid | null
  pending: PendingCounts
  created_at: string
  updated_at: string
}

export interface PendingMessage {
  id: Uuid
  delivery: Delivery
  position: number
  content: string
  created_at: string
}

export interface SessionDetail extends Session {
  pending_messages: PendingMessage[]
  /** Runtime state: whether an assistant turn is running right now. */
  is_generating: boolean
}

export type EntryType =
  | "message"
  | "tool_result"
  | "model_change"
  | "context_compaction"
  | "session_context"

export interface SessionEntry {
  id: Uuid
  sequence: number
  parent_id?: Uuid | null
  type: EntryType
  timestamp: string
  schema_version: number
  payload: Record<string, unknown>
}

export interface LlmConfigInput {
  provider: string
  model: string
  api_key: string
  reasoning_effort?: string
}

export interface LlmModelOption {
  id: string
  label: string
  context_size?: number | null
  reasoning_efforts: string[]
}

export interface LlmProviderOption {
  id: string
  label: string
  models: LlmModelOption[]
}

export interface LlmCatalog {
  providers: LlmProviderOption[]
}

export interface MessageInput {
  content: string
  delivery?: Delivery
  llm_config?: LlmConfigInput
}

export interface MessageAccepted {
  entry?: SessionEntry | null
  pending?: PendingMessage | null
  generation_started: boolean
}

export interface ResumeResponse {
  delivered: SessionEntry
  pending: PendingCounts
}

export interface Citation {
  citation_id: string
  paper_id: Uuid
  title_path?: string | null
  snippet: string
  page_start?: number | null
  page_end?: number | null
  chunk_ids: Uuid[]
}

export type SessionEventType =
  | "generation.started"
  | "message.delta"
  | "thinking.delta"
  | "trace.message"
  | "tool.started"
  | "tool.completed"
  | "queue.updated"
  | "generation.completed"
  | "generation.aborted"
  | "generation.failed"

export interface SessionEvent {
  event_id: string
  type: SessionEventType
  resource_id: Uuid
  sequence: number
  timestamp: string
  schema_version: number
  data: Record<string, unknown>
}

// --- Retrieval ------------------------------------------------------------
export type SearchScope = "library" | "project" | "paper"
export type SearchStatus = "ok" | "degraded" | "unavailable"
export type ChannelStatus = "ok" | "unavailable"

export interface SearchChannel {
  status: ChannelStatus
  result_count: number
  detail?: string | null
}

export interface SearchEvidence {
  paper_id: Uuid
  chunk_ids: Uuid[]
  title_path?: string | null
  snippet: string
  page_start?: number | null
  page_end?: number | null
  score: number
  keyword_rank?: number | null
  vector_rank?: number | null
}

export interface SearchResponse {
  query: string
  scope: SearchScope
  status: SearchStatus
  channels: Record<string, SearchChannel>
  evidence: SearchEvidence[]
}

export interface SearchInput {
  query: string
  scope?: SearchScope
  project_id?: Uuid
  paper_ids?: Uuid[]
  limit?: number
}

// --- Imports --------------------------------------------------------------
export type IdentifierType = "doi" | "arxiv"

/** The processing run a download joined, as the queue shows it. */
export interface QueueRun {
  status: RunStatus
  stage?: RunStage | null
  /** Stage name → ISO timestamp, for the stages that already finished. */
  stage_finished_at?: Record<string, string>
  error_message?: string | null
}

/**
 * One request the user made: fetching a file, then processing it.
 * A successful download is stitched to its run so both read as one process.
 */
export interface ImportQueueItem {
  /** Whether the request carried a download, or the file arrived with it. */
  source: "download" | "request"
  id: Uuid
  identifier: string
  /** An upload has no identifier, so the type records where it came from. */
  identifier_type: IdentifierType | "upload"
  status: DownloadStatus
  paper_id?: Uuid | null
  /** The current user's entry, usable with the library detail endpoint. */
  user_paper_id?: Uuid | null
  run_id?: Uuid | null
  project_id?: Uuid | null
  source_url?: string | null
  error_message?: string | null
  created_at: string
  finished_at?: string | null
  run?: QueueRun | null
}

/** The request just queued; processing happens in the background. */
export interface DownloadRead {
  id: Uuid
  identifier_type: IdentifierType
  identifier: string
  status: DownloadStatus
  created_at: string
}

export interface ImportApprovalPreview {
  candidates: Array<{
    title: string | null
    identifier: string
    source_id: string
  }>
}


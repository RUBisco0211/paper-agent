/**
 * Shared API types, mirroring the backend Pydantic schemas.
 *
 * Keep these in sync with the backend schemas (backend/app/<domain>/schemas.py):
 * the backend is the source of truth, and a field is optional here only when the
 * API may omit it.
 */

export type Uuid = string

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

export interface RegisterInput {
  email: string
  password: string
  display_name?: string
}

export interface LoginInput {
  email: string
  password: string
}

// --- Library --------------------------------------------------------------
export type PaperSource = "upload" | "doi" | "arxiv" | "manual"
export type MetadataStatus =
  | "recognized"
  | "partial"
  | "unrecognized"
  | "provider_failed"
  | "user_provided"

export interface Capabilities {
  has_pdf: boolean
  has_metadata: boolean
  has_fulltext: boolean
  has_keyword_index: boolean
  has_embedding: boolean
}

export type IngestionStage = "metadata" | "fulltext" | "chunking" | "embedding"
export type IngestionStatus = "queued" | "running" | "succeeded" | "failed"
export type StageStatus = "pending" | "running" | "succeeded" | "failed" | "skipped"

export interface IngestionStageState {
  stage: IngestionStage
  status: StageStatus
  attempt: number
  error_code?: string | null
  error_message?: string | null
  progress?: Record<string, unknown> | null
  started_at?: string | null
  finished_at?: string | null
}

export interface IngestionJob {
  id: Uuid
  paper_id: Uuid
  status: IngestionStatus
  current_stage?: IngestionStage | null
  error_code?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  stages: IngestionStageState[]
}

export interface ProcessingState {
  job_id?: Uuid | null
  status?: IngestionStatus | null
  current_stage?: IngestionStage | null
  error_code?: string | null
}

export interface UserPaperSummary {
  id: Uuid
  title: string | null
  authors: string[]
  year?: number | null
  venue?: string | null
  doi?: string | null
  arxiv_id?: string | null
  source: PaperSource
  original_filename?: string | null
  added_at: string
  capabilities: Capabilities
  processing: ProcessingState
}

export interface UserPaperDetail extends UserPaperSummary {
  abstract?: string | null
  metadata_status: MetadataStatus
  metadata?: Record<string, unknown> | null
  metadata_sources?: Array<Record<string, unknown>> | null
  pdf: {
    available: boolean
    page_count?: number | null
    byte_size?: number | null
  }
}

export interface UploadResponse {
  paper: UserPaperSummary
  ingestion_job?: IngestionJob | null
}

export interface MetadataCorrectionInput {
  title?: string
  authors?: string[]
  abstract?: string
  doi?: string
  arxiv_id?: string
  year?: number
  venue?: string
}

export interface MetadataCompletion {
  status: MetadataStatus
  source?: string | null
  error_code?: string | null
  applied_fields: string[]
}

export interface FetchPdfResponse extends UploadResponse {
  metadata: MetadataCompletion
}

export interface ResolveMetadataResponse {
  paper: UserPaperDetail
  metadata: MetadataCompletion
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
export type SessionScope = "library" | "project"
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
export type ChannelStatus = "ok" | "skipped" | "degraded" | "unavailable"

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
export type ImportStatus =
  | "queued"
  | "resolving"
  | "metadata_ready"
  | "pdf_unavailable"
  | "ready"
  | "failed"

export interface PaperImport {
  id: Uuid
  status: ImportStatus
  identifier_type: "doi" | "arxiv"
  identifier: string
  paper_id?: Uuid | null
  project_id?: Uuid | null
  metadata_source?: string | null
  error_code?: string | null
  created_at: string
  updated_at: string
  finished_at?: string | null
}

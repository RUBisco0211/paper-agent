export type MessageQuote = {
  kind: "message"
  source_message_id: string
  block_index: number
  start: number
  end: number
  selected_text: string
  comment: string
}

export type PaperQuote = {
  /** Markdown 全文引用没有页码，它引用的是整篇解析产物。 */
  kind: "parsed_block" | "pdf_selection" | "markdown_selection"
  user_paper_id: string
  version: string
  page?: number | null
  block_id?: number
  start?: number
  end?: number
  rects?: number[][]
  selected_text: string
  comment: string
  source_title?: string
  include_image?: boolean
}

export type QuoteReference = MessageQuote | PaperQuote

export interface ToolSearchEvidence {
  citation_id: string
  snippet: string
  page_start: number | null
  page_end: number | null
}

/**
 * What the conversation sidebar reader can show for one paper entry.
 *
 * A plain entry has no locator; a located reference points at one parsed block
 * or PDF selection. They share one shape so a click and a citation take the
 * same path into the reader.
 */
export interface PaperOpenReference {
  kind: "paper" | "parsed_block" | "pdf_selection"
  user_paper_id: string
  page: number | null
  block_id?: number
  selected_text?: string
  comment?: string
}

export type PaperOpen = (reference: PaperOpenReference) => boolean
/** Registers a sidebar opener; the returned function unregisters it. */
export type PaperOpenRegistrar = (opener: PaperOpen) => () => void

/**
 * One paper as the agent's `list_papers` tool receives it.
 *
 * Deliberately narrower than a library entry: the internal list endpoint sends
 * the user's entry id plus just enough to recognise the paper and its state.
 */
export interface ToolListedPaper {
  paper_id: string
  title: string | null
  authors?: string[] | null
  year?: number | null
  venue?: string | null
  has_parsed?: boolean
}

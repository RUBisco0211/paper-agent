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
  kind: "parsed_block" | "pdf_selection"
  user_paper_id: string
  version: string
  page: number
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

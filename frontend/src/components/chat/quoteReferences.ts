import type { MessageQuote, QuoteReference } from "@/types/chat"

/** Discard invalid PDF text rectangles while preserving every selected fragment. */
export function normalizePdfQuoteRects(rects: number[][]): number[][] {
  return rects.flatMap((rect) => {
    if (rect.length !== 4 || rect.some((value) => !Number.isFinite(value))) return []
    const [left, top, right, bottom] = rect.map((value) => Math.max(0, Math.min(1, value)))
    return right > left && bottom > top ? [[left, top, right, bottom]] : []
  })
}

export function messageQuoteKey(reference: MessageQuote): string {
  return `${reference.source_message_id}:${reference.block_index}:${reference.start}:${reference.end}:${reference.selected_text}:${reference.comment}`
}

export function messageReferenceFromSelection(
  sourceMessageId: string, blockIndex: number, start: number, end: number,
  selectedText: string, comment: string,
): MessageQuote {
  return { kind: 'message', source_message_id: sourceMessageId, block_index: blockIndex,
    start, end, selected_text: selectedText, comment }
}

export function readQuoteReferences(metadata: unknown): QuoteReference[] {
  if (!metadata || typeof metadata !== 'object') return []
  const paperAgent = (metadata as Record<string, unknown>).paper_agent
  if (!paperAgent || typeof paperAgent !== 'object') return []
  const refs = (paperAgent as Record<string, unknown>).references
  if (!Array.isArray(refs)) return []
  return refs.filter((ref): ref is QuoteReference =>
    typeof ref === 'object' && ref !== null &&
    ['message', 'parsed_block', 'pdf_selection', 'markdown_selection'].includes(ref.kind) &&
    typeof ref.selected_text === 'string' && typeof ref.comment === 'string')
}

export function readQuotedBody(metadata: unknown): string | null {
  if (!metadata || typeof metadata !== 'object') return null
  const value = (metadata as Record<string, unknown>).paper_agent
  if (!value || typeof value !== 'object') return null
  const body = (value as Record<string, unknown>).body
  return typeof body === 'string' ? body : null
}

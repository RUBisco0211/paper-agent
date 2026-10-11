import { createContext } from "react"

import type { QuoteReference } from "@upstream/components/chat/quote-references"

export type ChatQuoteReceiver = (reference: QuoteReference) => boolean
export type PaperQuoteOpener = (reference: Extract<QuoteReference, { kind: 'parsed_block' | 'pdf_selection' }>) => boolean

export const ChatQuoteContext = createContext<{
  register: (sessionId: string, receiver: ChatQuoteReceiver) => () => void
  add: (sessionId: string, reference: QuoteReference) => boolean
  registerPaperOpener: (sessionId: string, opener: PaperQuoteOpener) => () => void
  openPaper: (sessionId: string, reference: Extract<QuoteReference, { kind: 'parsed_block' | 'pdf_selection' }>) => boolean
} | null>(null)

import { createContext } from "react"

import type { PaperOpenRegistrar, QuoteReference } from "@/types/chat"

export type ChatQuoteReceiver = (reference: QuoteReference) => boolean
export type PaperQuoteOpener = (reference: Extract<QuoteReference, { kind: 'parsed_block' | 'pdf_selection' }>) => boolean

export const ChatQuoteContext = createContext<{
  register: (sessionId: string, receiver: ChatQuoteReceiver) => () => void
  add: (sessionId: string, reference: QuoteReference) => boolean
  registerPaperOpener: (sessionId: string, opener: PaperQuoteOpener) => () => void
  openPaper: (sessionId: string, reference: Extract<QuoteReference, { kind: 'parsed_block' | 'pdf_selection' }>) => boolean
  /** Registers a sidebar reader for tool-clicked entries; null outside a conversation. */
  openEntry: PaperOpenRegistrar | null
} | null>(null)

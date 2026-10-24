import { createContext, useContext, type ReactNode } from "react"

import type { PaperOpen } from "@/types/chat"

const CitationContext = createContext<((citationId: string) => void) | null>(null)
const PaperOpenContext = createContext<PaperOpen | null>(null)

export function CitationProvider({
  onOpen,
  onOpenPaper,
  children,
}: {
  onOpen: (citationId: string) => void
  /** Opens a paper entry in the conversation sidebar; absent outside a chat. */
  onOpenPaper?: PaperOpen
  children: ReactNode
}) {
  return (
    <CitationContext.Provider value={onOpen}>
      <PaperOpenContext.Provider value={onOpenPaper ?? null}>
        {children}
      </PaperOpenContext.Provider>
    </CitationContext.Provider>
  )
}

export function useCitationOpen() {
  return useContext(CitationContext)
}

export function usePaperOpen() {
  return useContext(PaperOpenContext)
}

import { createContext, useContext, type ReactNode } from "react"

const CitationContext = createContext<((citationId: string) => void) | null>(null)

export function CitationProvider({
  onOpen,
  children,
}: {
  onOpen: (citationId: string) => void
  children: ReactNode
}) {
  return <CitationContext.Provider value={onOpen}>{children}</CitationContext.Provider>
}

export function useCitationOpen() {
  return useContext(CitationContext)
}

import { createContext, useContext, type ReactNode } from "react"

const AgentUiContext = createContext(false)

export function AgentUiProvider({ children }: { children: ReactNode }) {
  return <AgentUiContext.Provider value>{children}</AgentUiContext.Provider>
}

export function useAgentUi() {
  return useContext(AgentUiContext)
}

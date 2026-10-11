export interface ChatTabsState {
  paths: string[]
  activePath: string
}

export function isDraftTabPath(path: string): boolean {
  return path === "/chat/new"
}

export function isChatTabPath(path: string): boolean {
  return isDraftTabPath(path) || /^\/chat\/[^/]+\/[^/]+$/.test(path) && !path.startsWith("/chat/project/")
}

export function readChatTabs(saved: string | null): ChatTabsState {
  try {
    const parsed: unknown = JSON.parse(saved ?? "null")
    if (!parsed || typeof parsed !== "object") throw new Error("invalid tabs")
    const record = parsed as Record<string, unknown>
    const paths = Array.isArray(record.paths)
      ? [...new Set(record.paths.filter((path): path is string => typeof path === "string" && isChatTabPath(path)))].slice(0, 20)
      : []
    const activePath = typeof record.activePath === "string" && paths.includes(record.activePath) ? record.activePath : paths[0]
    return { paths, activePath: activePath ?? "/chat" }
  } catch {
    return { paths: [], activePath: "/chat" }
  }
}

export function closeChatTab(paths: string[], closingPath: string, activePath: string): ChatTabsState {
  const index = paths.indexOf(closingPath)
  const remaining = paths.filter((path) => path !== closingPath)
  if (!remaining.length) return { paths: [], activePath: "/chat" }
  return {
    paths: remaining,
    activePath: closingPath === activePath ? remaining[Math.min(index, remaining.length - 1)] : activePath,
  }
}

export function replaceDraftTab(paths: string[], draftPath: string, sessionPath: string): string[] {
  const index = paths.indexOf(draftPath)
  const withoutSession = paths.filter((path) => path !== sessionPath)
  if (index < 0) return [...withoutSession, sessionPath]
  return withoutSession.map((path) => path === draftPath ? sessionPath : path)
}

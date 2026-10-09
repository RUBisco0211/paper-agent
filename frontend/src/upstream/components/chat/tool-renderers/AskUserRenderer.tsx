import type { ToolRenderer } from "./types"

export const AskUserRenderer: ToolRenderer = {
  renderHeader: () => <span>向你提问</span>,
  renderBody: (pair) => pair.result?.state === "success"
    ? <p className="py-2 text-xs text-muted-foreground">已提交答案</p>
    : null,
}

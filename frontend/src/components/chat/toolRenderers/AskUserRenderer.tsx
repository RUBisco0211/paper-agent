import type { ToolRenderer } from "./types"
import { parseAskUserQuestions } from "@/components/chat/AskUserQuestionnaire"
import { getResultText } from "@/components/chat/toolRenderers/shared"

function submittedAnswers(output: string): Record<string, string | string[] | null> | null {
  try {
    const parsed: unknown = JSON.parse(output)
    if (!parsed || typeof parsed !== "object" || !("answers" in parsed) || !parsed.answers || typeof parsed.answers !== "object" || Array.isArray(parsed.answers)) return null
    return parsed.answers as Record<string, string | string[] | null>
  } catch {
    return null
  }
}

export const AskUserRenderer: ToolRenderer = {
  renderHeader: () => <span>向你提问</span>,
  renderBody: (pair) => {
    if (!pair.result) return null
    const output = getResultText(pair.result)
    if (pair.result.state !== "success") return <p className="py-2 text-xs text-destructive">提问未完成</p>
    const answers = submittedAnswers(output)
    const questions = parseAskUserQuestions(pair.call.input)
    if (!answers || !questions.length || "error" in answers) return <p className="py-2 text-xs text-muted-foreground">{output}</p>
    return <dl className="space-y-2 py-2 text-xs">
      {questions.map((question, index) => {
        const answer = answers[question.name]
        const values = Array.isArray(answer) ? answer : answer == null ? [] : [answer]
        const display = values.map((value) => question.options.find((option) => option.value === value)?.label ?? value).join("、")
        return <div key={question.name}>
          <dt className="text-muted-foreground">{index + 1}. {question.prompt}</dt>
          <dd className="mt-0.5 whitespace-pre-wrap break-words">{display || "已跳过"}</dd>
        </div>
      })}
    </dl>
  },
}

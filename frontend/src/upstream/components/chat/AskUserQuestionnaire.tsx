import { Questionnaire } from "@shadcn/react/questionnaire"
import type { ToolCallBlock } from "@agentscope-ai/agentscope/message"
import { useRef, useState, type FormEvent } from "react"

import { Button } from "@upstream/components/ui/button"

type Question = {
  name: string
  prompt: string
  description?: string
  type: "single" | "multiple" | "text"
  required: boolean
  options: Array<{ value: string; label: string }>
  allowOther: boolean
}

export function parseAskUserQuestions(input: string): Question[] {
  try {
    const raw: unknown = JSON.parse(input)
    if (!raw || typeof raw !== "object" || !("questions" in raw) || !Array.isArray(raw.questions)) return []
    const result: Question[] = []
    for (const item of raw.questions.slice(0, 3)) {
      if (!item || typeof item !== "object" || typeof item.name !== "string" || typeof item.prompt !== "string") return []
      if (!/^[a-zA-Z][\w-]{0,39}$/.test(item.name) || !item.prompt.trim() || !["single", "multiple", "text"].includes(item.type)) return []
      if (result.some((question) => question.name === item.name)) return []
      const options = Array.isArray(item.options) ? item.options.filter((option: unknown): option is { value: string; label: string } =>
        Boolean(option && typeof option === "object" && "value" in option && "label" in option && typeof option.value === "string" && typeof option.label === "string"),
      ).slice(0, 7) : []
      if (item.type !== "text" && options.length < 2) return []
      result.push({
        name: item.name, prompt: item.prompt.trim(),
        description: typeof item.description === "string" ? item.description : undefined,
        type: item.type, required: item.required !== false,
        options, allowOther: item.allow_other === true,
      })
    }
    return result
  } catch {
    return []
  }
}

export function AskUserQuestionnaire({ toolCall, onAnswer }: {
  toolCall: ToolCallBlock
  onAnswer: (answers: Record<string, string | string[] | null>) => Promise<void>
}) {
  const questions = parseAskUserQuestions(toolCall.input)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const submittingRef = useRef(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submittingRef.current) return
    submittingRef.current = true
    setSubmitting(true)
    setError("")
    const form = new FormData(event.currentTarget)
    const answers = Object.fromEntries(questions.map((question) => {
      const values = form.getAll(question.name).map(String).map((value) => value.trim()).filter(Boolean)
      return [question.name, question.type === "multiple" ? values : values[0] ?? null]
    })) as Record<string, string | string[] | null>
    try {
      await onAnswer(answers)
    } catch {
      submittingRef.current = false
      setSubmitting(false)
      setError("提交失败，请重试")
    }
  }

  if (!questions.length) return (
    <div className="rounded-2xl border bg-background p-4 text-sm">
      <p>问题无法显示</p>
      <Button size="sm" className="mt-3" disabled={submitting} onClick={() => void onAnswer({ error: "invalid_questions" })}>请重新提问</Button>
    </div>
  )

  return <div className="rounded-2xl border bg-background p-4 shadow-sm">
    <Questionnaire.Root items={questions.map((question) => ({ name: question.name, required: question.required, choices: question.options }))} onSubmit={(event) => void submit(event)}>
      <Questionnaire.Progress className="mb-3 text-xs text-muted-foreground" />
      {questions.map((question) => <Questionnaire.Item key={question.name} name={question.name} required={question.required} multiple={question.type === "multiple"} className="flex flex-col gap-3 border-0 p-0">
        <Questionnaire.Title className="text-sm font-medium">{question.prompt}</Questionnaire.Title>
        {question.description && <Questionnaire.Description className="text-xs text-muted-foreground">{question.description}</Questionnaire.Description>}
        <Questionnaire.Choices className="flex flex-col gap-2">
          {question.options.map((option) => <Questionnaire.Choice key={option.value} value={option.value} className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm data-[checked]:border-primary">
            <Questionnaire.ChoiceInput className="accent-primary" />
            <Questionnaire.ChoiceLabel>{option.label}</Questionnaire.ChoiceLabel>
          </Questionnaire.Choice>)}
          {(question.type === "text" || question.allowOther) && <Questionnaire.Input aria-label={question.type === "text" ? "填写答案" : "其他答案"} placeholder="填写答案" className="h-9 rounded-md border bg-background px-3 text-sm" />}
        </Questionnaire.Choices>
        <Questionnaire.Error className="text-xs text-destructive" />
      </Questionnaire.Item>)}
      {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <Questionnaire.Previous render={<Button variant="ghost" size="sm" />} disabled={submitting}>上一题</Questionnaire.Previous>
        <Questionnaire.Skip render={<Button variant="ghost" size="sm" />} disabled={submitting}>跳过</Questionnaire.Skip>
        <Questionnaire.Next render={<Button variant="outline" size="sm" />} disabled={submitting}>下一题</Questionnaire.Next>
        <Questionnaire.Submit render={<Button size="sm" />} disabled={submitting}>{submitting ? "提交中…" : "提交答案"}</Questionnaire.Submit>
      </div>
    </Questionnaire.Root>
  </div>
}

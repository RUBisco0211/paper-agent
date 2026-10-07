import type { Api } from "@/lib/api"
import { scheduleApi } from "@upstream/api/schedule"
import type { ChatModelConfig, ScheduleRecord } from "@upstream/api/types"

export interface ProjectSchedule {
  schedule: ScheduleRecord
  projectId: string | null
}

interface ScheduleBinding {
  schedule_id: string
  project_id: string | null
}

const BINDINGS = "/v1/schedule-bindings"

export async function listProjectSchedules(api: Api): Promise<ProjectSchedule[]> {
  const [bindings, scheduleResult] = await Promise.all([
    api.client.request<ScheduleBinding[]>(BINDINGS),
    scheduleApi.list(),
  ])
  const byId = new Map(bindings.map((binding) => [binding.schedule_id, binding.project_id]))
  return scheduleResult.schedules.flatMap((schedule) => {
    const projectId = byId.get(schedule.id)
    return byId.has(schedule.id) ? [{ schedule, projectId: projectId ?? null }] : []
  })
}

export async function createProjectSchedule(
  api: Api,
  input: {
    projectId: string | null
    name: string
    prompt: string
    cronExpression: string
    timezone: string
    agentId: string
    model: ChatModelConfig
  },
): Promise<string> {
  const { schedule_id: scheduleId } = await scheduleApi.create({
    name: input.name,
    description: input.prompt,
    cron_expression: input.cronExpression,
    timezone: input.timezone,
    agent_id: input.agentId,
    chat_model_config: input.model,
    enabled: false,
    stateful: false,
    permission_mode: "dont_ask",
  })
  let bound = false
  try {
    await api.client.request(BINDINGS, {
      method: "POST",
      json: { schedule_id: scheduleId, project_id: input.projectId },
    })
    bound = true
    await scheduleApi.update(scheduleId, { enabled: true })
    return scheduleId
  } catch (cause) {
    try {
      await scheduleApi.delete(scheduleId)
      if (bound) await api.client.request(`${BINDINGS}/${scheduleId}`, { method: "DELETE" })
    } catch (cleanupError) {
      throw new AggregateError([cause, cleanupError], "创建定时任务失败，清理未完成")
    }
    throw cause
  }
}

export async function deleteProjectSchedule(api: Api, scheduleId: string): Promise<void> {
  await scheduleApi.delete(scheduleId)
  await api.client.request(`${BINDINGS}/${scheduleId}`, { method: "DELETE" })
}

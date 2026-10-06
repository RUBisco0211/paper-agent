import { beforeEach, expect, it, vi } from "vitest"

const { create, update, remove } = vi.hoisted(() => ({
  create: vi.fn(), update: vi.fn(), remove: vi.fn(),
}))
vi.mock("@upstream/api/schedule", () => ({ scheduleApi: { create, update, delete: remove } }))

import { createProjectSchedule } from "./project-schedules"

beforeEach(() => {
  vi.clearAllMocks()
  create.mockResolvedValue({ schedule_id: "schedule-1" })
  update.mockResolvedValue({})
  remove.mockResolvedValue(undefined)
})

it("binds a paused task to its project before enabling scheduled runs", async () => {
  const request = vi.fn().mockResolvedValue({ schedule_id: "schedule-1", project_id: "project-1" })
  await createProjectSchedule({ client: { request } } as never, {
    projectId: "project-1",
    name: "Weekly review",
    prompt: "Summarize this project",
    cronExpression: "0 9 * * 1",
    timezone: "Asia/Shanghai",
    agentId: "agent-1",
    model: { type: "deepseek_credential", credential_id: "cred-1", model: "deepseek-chat", parameters: {} },
  })
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ enabled: false, stateful: false }))
  expect(request).toHaveBeenCalledWith("/v1/schedule-bindings", expect.objectContaining({
    method: "POST", json: { schedule_id: "schedule-1", project_id: "project-1" },
  }))
  expect(update).toHaveBeenCalledWith("schedule-1", { enabled: true })
  expect(create.mock.invocationCallOrder[0]).toBeLessThan(request.mock.invocationCallOrder[0])
  expect(request.mock.invocationCallOrder[0]).toBeLessThan(update.mock.invocationCallOrder[0])
})

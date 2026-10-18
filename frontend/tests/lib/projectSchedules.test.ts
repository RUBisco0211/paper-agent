import { beforeEach, expect, it, vi } from "vitest";

const { create, update, remove, list } = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  list: vi.fn(),
}));
vi.mock("@/lib/api/agentscope/schedule", () => ({
  scheduleApi: { create, update, delete: remove, list },
}));

import {
  createProjectSchedule,
  listProjectSchedules,
} from "@/lib/projectSchedules";

beforeEach(() => {
  vi.clearAllMocks();
  create.mockResolvedValue({ schedule_id: "schedule-1" });
  update.mockResolvedValue({});
  remove.mockResolvedValue(undefined);
});

it("binds a paused task to its project before enabling scheduled runs", async () => {
  const request = vi
    .fn()
    .mockResolvedValue({ schedule_id: "schedule-1", project_id: "project-1", notify_email: false });
  await createProjectSchedule({ client: { request } } as never, {
    projectId: "project-1",
    name: "Weekly review",
    prompt: "Summarize this project",
    cronExpression: "0 9 * * 1",
    timezone: "Asia/Shanghai",
    agentId: "agent-1",
    model: {
      type: "deepseek_credential",
      credential_id: "cred-1",
      model: "deepseek-chat",
      parameters: {},
    },
  });
  expect(create).toHaveBeenCalledWith(
    expect.objectContaining({ enabled: false, stateful: false }),
  );
  expect(request).toHaveBeenCalledWith(
    "/v1/schedule-bindings",
    expect.objectContaining({
      method: "POST",
      json: {
        schedule_id: "schedule-1",
        project_id: "project-1",
        notify_email: false,
      },
    }),
  );
  expect(update).toHaveBeenCalledWith("schedule-1", { enabled: true });
  expect(create.mock.invocationCallOrder[0]).toBeLessThan(
    request.mock.invocationCallOrder[0],
  );
  expect(request.mock.invocationCallOrder[0]).toBeLessThan(
    update.mock.invocationCallOrder[0],
  );
});

it("manual creation carries email notification consent when the user enables it", async () => {
  const request = vi.fn().mockResolvedValue({});
  await createProjectSchedule({ client: { request } } as never, {
    projectId: null,
    name: "提醒",
    prompt: "总结",
    cronExpression: "0 9 * * *",
    timezone: "UTC",
    agentId: "agent-1",
    notify_email: true,
    model: {
      type: "deepseek_credential",
      credential_id: "cred-1",
      model: "deepseek-chat",
      parameters: {},
    },
  });
  expect(request).toHaveBeenCalledWith("/v1/schedule-bindings", {
    method: "POST",
    json: { schedule_id: "schedule-1", project_id: null, notify_email: true },
  });
});

it("schedule listing reads notification consent from the binding when schedules are joined", async () => {
  const request = vi
    .fn()
    .mockResolvedValue([
      { schedule_id: "schedule-1", project_id: null, notify_email: true },
    ]);
  list.mockResolvedValue({
    schedules: [
      { id: "schedule-1", data: {} },
      { id: "unbound", data: {} },
    ],
  });
  expect(await listProjectSchedules({ client: { request } } as never)).toEqual([
    {
      schedule: { id: "schedule-1", data: {} },
      projectId: null,
      notify_email: true,
    },
  ]);
});

import { expect, it } from "vitest"

import { calendarCronExpression, cronForFrequency } from "@/components/schedule/scheduleFrequency"

it("maps each weekly frequency to the selected days at the chosen time", () => {
  expect(cronForFrequency("daily", "09:30", [])).toBe("30 9 * * *")
  expect(cronForFrequency("weekly", "09:30", [3])).toBe("30 9 * * wed")
  expect(cronForFrequency("weekdays", "09:30", [])).toBe("30 9 * * mon-fri")
  expect(cronForFrequency("weekends", "09:30", [])).toBe("30 9 * * sat,sun")
  expect(cronForFrequency("custom", "09:30", [5, 1, 3])).toBe("30 9 * * mon,wed,fri")
  expect(() => cronForFrequency("custom", "09:30", [])).toThrow()
})

it("shows earlier numeric AgentScope weekdays on their actual calendar days", () => {
  expect(calendarCronExpression("30 9 * * 0")).toBe("30 9 * * mon")
  expect(calendarCronExpression("30 9 * * 0,6")).toBe("30 9 * * mon,sun")
})

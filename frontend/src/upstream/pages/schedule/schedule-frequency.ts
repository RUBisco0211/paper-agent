export type ScheduleFrequency = "daily" | "weekly" | "weekdays" | "weekends" | "custom"

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
const CRON_DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
const APS_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

export function cronForFrequency(frequency: ScheduleFrequency, time: string, days: number[]): string {
  const match = /^(\d{2}):(\d{2})$/.exec(time)
  if (!match) throw new Error("请选择有效时间")
  const hour = Number(match[1])
  const minute = Number(match[2])
  if (hour > 23 || minute > 59) throw new Error("请选择有效时间")
  const selected = [...new Set(days)].sort((a, b) => a - b)
  if (selected.some((day) => !Number.isInteger(day) || day < 0 || day > 6)) throw new Error("请选择有效星期")

  let weekday = "*"
  if (frequency === "weekly") {
    if (selected.length !== 1) throw new Error("请选择一个星期几")
    weekday = CRON_DAYS[selected[0]]
  } else if (frequency === "weekdays") {
    weekday = "mon-fri"
  } else if (frequency === "weekends") {
    weekday = "sat,sun"
  } else if (frequency === "custom") {
    if (selected.length === 0) throw new Error("请至少选择一天")
    weekday = selected.map((day) => CRON_DAYS[day]).join(",")
  }
  return `${minute} ${hour} * * ${weekday}`
}

export function calendarCronExpression(cron: string): string {
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return cron
  parts[4] = parts[4].split(",").map((part) => {
    if (/^[0-6]$/.test(part)) return APS_DAYS[Number(part)]
    if (/^[0-6]-[0-6]$/.test(part)) {
      const [start, end] = part.split("-").map(Number)
      return `${APS_DAYS[start]}-${APS_DAYS[end]}`
    }
    return part
  }).join(",")
  return parts.join(" ")
}

export function describeScheduleFrequency(cron: string): string {
  const weekday = calendarCronExpression(cron).trim().split(/\s+/)[4]
  if (weekday === "*") return "每天"
  if (weekday === "mon-fri") return "工作日"
  if (weekday === "sat,sun" || weekday === "sun,sat") return "周末"
  const days = weekday?.split(",").map((day) => CRON_DAYS.indexOf(day))
  if (days?.length && days.every((day) => day >= 0)) {
    return `每周 ${days.map((day) => WEEKDAYS[day]).join("、")}`
  }
  return "按计划"
}

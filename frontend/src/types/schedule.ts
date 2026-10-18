import type { ChatModelConfig, ScheduleRecord } from "./agent"

export interface ProjectSchedule {
  schedule: ScheduleRecord
  projectId: string | null
  notify_email: boolean
}

export interface ScheduleBinding {
  schedule_id: string
  project_id: string | null
  notify_email: boolean
}

export interface ScheduleDraft {
  name: string
  prompt: string
  cronExpression: string
  timezone: string
  model: ChatModelConfig
  notify_email: boolean
}

export interface ReviewedSchedule {
  name: string
  prompt: string
  time: string
  weekdays: string[]
  notify_email: boolean
}

export type ScheduleFrequency =
  | "daily"
  | "weekly"
  | "weekdays"
  | "weekends"
  | "custom"

export type ParsedScheduleFrequency =
  | "daily"
  | "weekly"
  | "monthly"
  | "once"
  | "custom"

export interface ParsedSchedule {
  frequency: ParsedScheduleFrequency
  time: string
  weekday?: number
  dayOfMonth?: number
  date?: Date
}

export interface ScheduleEvent {
  id: string
  title: string
  date: string
  time: string
  content: string
  location?: string
  attendees?: string[]
}

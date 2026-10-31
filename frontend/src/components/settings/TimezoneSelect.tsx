import { useMemo } from "react"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select"

//: 浏览器不支持 Intl.supportedValuesOf 时的兜底，够日常使用。
const FALLBACK_ZONES = [
  "UTC",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Asia/Singapore",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
]

function zoneOptions(current: string): string[] {
  let zones: string[] = []
  try {
    zones = Intl.supportedValuesOf("timeZone")
  } catch {
    zones = []
  }
  const options = zones.length > 0 ? zones : FALLBACK_ZONES
  // 旧数据里可能存着列表外的时区，仍然要能显示与保留。
  return current && !options.includes(current) ? [current, ...options] : options
}

/** 只能从 IANA 时区里选，避免手输拼错导致定时任务跑错时间。 */
export function TimezoneSelect({
  id,
  value,
  onChange,
  disabled,
}: {
  id?: string
  value: string
  onChange: (timezone: string) => void
  disabled?: boolean
}) {
  const options = useMemo(() => zoneOptions(value), [value])
  return <Select value={value} onValueChange={onChange} disabled={disabled}>
    <SelectTrigger id={id} className="w-full">
      <SelectValue placeholder="选择时区" />
    </SelectTrigger>
    <SelectContent>
      {options.map((zone) => <SelectItem key={zone} value={zone}>{zone}</SelectItem>)}
    </SelectContent>
  </Select>
}

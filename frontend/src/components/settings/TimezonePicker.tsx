import { Check, ChevronsUpDown } from "lucide-react"
import { useMemo, useState } from "react"

import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/Popover"

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

/** 只能从 IANA 时区里选，输入关键字过滤，避免手输拼错导致定时任务跑错时间。 */
export function TimezonePicker({
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
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const options = useMemo(() => zoneOptions(value), [value])
  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return options
    return options.filter((zone) => zone.toLowerCase().includes(needle))
  }, [options, query])

  function choose(zone: string) {
    onChange(zone)
    setOpen(false)
    setQuery("")
  }

  return <Popover
    open={open}
    onOpenChange={(next) => {
      setOpen(next)
      if (!next) setQuery("")
    }}
  >
    <PopoverTrigger asChild>
      <Button
        id={id}
        type="button"
        variant="outline"
        size="sm"
        role="combobox"
        aria-expanded={open}
        aria-label="时区"
        className="w-full justify-between font-normal"
        disabled={disabled}
      >
        <span className="truncate">{value || "选择时区"}</span>
        <ChevronsUpDown className="text-muted-foreground" />
      </Button>
    </PopoverTrigger>
    <PopoverContent align="start" className="w-(--radix-popover-trigger-width) p-0">
      <div className="border-b p-2">
        <Input
          autoFocus
          aria-label="搜索时区"
          placeholder="搜索时区"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && matches[0]) {
              event.preventDefault()
              choose(matches[0])
            }
          }}
        />
      </div>
      <div role="listbox" aria-label="时区选项" className="max-h-64 overflow-y-auto p-1">
        {matches.length === 0 && <p className="px-2 py-3 text-sm text-muted-foreground">没有匹配的时区</p>}
        {matches.map((zone) => <button
          key={zone}
          type="button"
          role="option"
          aria-selected={zone === value}
          onClick={() => choose(zone)}
          className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-muted"
        >
          <span className="truncate">{zone}</span>
          {zone === value && <Check className="size-4 shrink-0" />}
        </button>)}
      </div>
    </PopoverContent>
  </Popover>
}

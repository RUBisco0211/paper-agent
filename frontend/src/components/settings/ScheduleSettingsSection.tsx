import { useState } from "react"

import { useAuth } from "@/components/providers/AuthProvider"
import { TimezonePicker } from "@/components/settings/TimezonePicker"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemSeparator,
  ItemTitle,
} from "@/components/ui/Item"
import { Switch } from "@/components/ui/Switch"
import { notifyError } from "@/lib/errors"

export function ScheduleSettingsSection() {
  const { preferences, setTimezone, setNotifyEmailDefault } = useAuth()
  const [saving, setSaving] = useState(false)

  async function save(action: () => Promise<void>) {
    setSaving(true)
    try {
      await action()
    } catch (error) {
      notifyError(error, "保存失败，请稍后重试")
    } finally {
      setSaving(false)
    }
  }

  const timezone = preferences?.timezone
    ?? Intl.DateTimeFormat().resolvedOptions().timeZone
    ?? "UTC"

  return <ItemGroup>
    <Item>
      <ItemContent>
        <ItemTitle>时区</ItemTitle>
        <ItemDescription>定时任务按这个时区执行。</ItemDescription>
      </ItemContent>
      <ItemActions>
        <div className="w-64">
          <TimezonePicker
            id="timezone"
            value={timezone}
            disabled={saving}
            onChange={(next) => void save(() => setTimezone(next))}
          />
        </div>
      </ItemActions>
    </Item>
    <ItemSeparator />
    <Item>
      <ItemContent>
        <ItemTitle>邮件通知</ItemTitle>
        <ItemDescription>新建定时任务时默认发送邮件通知。</ItemDescription>
      </ItemContent>
      <ItemActions>
        <Switch
          id="notify-email-default"
          aria-label="邮件通知"
          checked={preferences?.notify_email_default ?? false}
          disabled={saving}
          onCheckedChange={(checked) => void save(() => setNotifyEmailDefault(checked))}
        />
      </ItemActions>
    </Item>
  </ItemGroup>
}

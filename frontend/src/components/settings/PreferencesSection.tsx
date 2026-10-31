import { useState } from "react"

import { useAuth } from "@/components/providers/AuthProvider"
import { THEMES, useTheme } from "@/components/providers/ThemeProvider"
import { TimezoneSelect } from "@/components/settings/TimezoneSelect"
import { Switch } from "@/components/ui/Switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select"
import { notifyError } from "@/lib/errors"

export function PreferencesSection() {
  const { theme, setTheme } = useTheme()
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

  return <div className="flex flex-col gap-5">
    <section className="rounded-lg border p-5">
      <h2 className="mb-1 font-medium">外观</h2>
      <p className="mb-4 text-sm text-muted-foreground">主题只保存在这台设备的浏览器里。</p>
      <div className="flex items-center justify-between gap-4">
        <label htmlFor="theme" className="text-sm">主题</label>
        <Select value={theme} onValueChange={(value) => setTheme(value as typeof theme)}>
          <SelectTrigger id="theme" className="w-44" aria-label="主题">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {THEMES.map((item) => <SelectItem key={item.id} value={item.id}>{item.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
    </section>

    <section className="rounded-lg border p-5">
      <h2 className="mb-1 font-medium">时区</h2>
      <p className="mb-4 text-sm text-muted-foreground">定时任务按这个时区执行；首次登录会按浏览器自动填一次。</p>
      <div className="flex items-center justify-between gap-4">
        <label htmlFor="timezone" className="text-sm">本地时区</label>
        <div className="w-64">
          <TimezoneSelect
            id="timezone"
            value={preferences?.timezone ?? ""}
            disabled={saving || !preferences}
            onChange={(timezone) => void save(() => setTimezone(timezone))}
          />
        </div>
      </div>
    </section>

    <section className="rounded-lg border p-5">
      <h2 className="mb-1 font-medium">邮件通知</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        新建定时任务时的默认值；单个任务里仍然可以改。通知只发到已验证的邮箱。
      </p>
      <div className="flex items-center justify-between gap-4">
        <label htmlFor="notify-email-default" className="text-sm">任务完成后默认发邮件</label>
        <Switch
          id="notify-email-default"
          checked={preferences?.notify_email_default ?? false}
          disabled={saving || !preferences}
          onCheckedChange={(checked) => void save(() => setNotifyEmailDefault(checked))}
        />
      </div>
    </section>
  </div>
}

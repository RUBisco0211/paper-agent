import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/lib/auth/provider"
import { fieldErrors, notifyError, notifySuccess } from "@/lib/errors"

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      await register({
        email,
        password,
        display_name: displayName || undefined,
      })
      notifySuccess("注册成功", "先配置模型，再上传第一篇论文")
      navigate("/settings", { replace: true })
    } catch (error) {
      const fields = fieldErrors(error)
      setErrors(fields)
      if (Object.keys(fields).length === 0) {
        notifyError(error, "注册失败")
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-muted/30 flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>创建账号</CardTitle>
          <CardDescription>
            个人论文库、项目与会话彼此隔离，不会与其他账号共享。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">邮箱</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={Boolean(errors.email)}
                required
              />
              {errors.email ? (
                <p className="text-destructive text-xs">{errors.email}</p>
              ) : null}
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="display_name">显示名称（可选）</Label>
              <Input
                id="display_name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={Boolean(errors.password)}
                required
              />
              {errors.password ? (
                <p className="text-destructive text-xs">{errors.password}</p>
              ) : (
                <p className="text-muted-foreground text-xs">至少 8 个字符</p>
              )}
            </div>
            <Button type="submit" disabled={submitting}>
              {submitting ? "注册中…" : "注册"}
            </Button>
            <p className="text-muted-foreground text-center text-sm">
              已有账号？{" "}
              <Link className="text-foreground underline" to="/login">
                登录
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

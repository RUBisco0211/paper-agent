import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
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
      await register({ email, password, display_name: displayName || undefined })
      notifySuccess("注册成功")
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
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
            <FieldGroup>
              <Field data-invalid={Boolean(errors.email)}>
                <FieldLabel htmlFor="email">邮箱</FieldLabel>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  aria-invalid={Boolean(errors.email)}
                  required
                />
                <FieldError>{errors.email}</FieldError>
              </Field>
              <Field>
                <FieldLabel htmlFor="display_name">显示名称</FieldLabel>
                <Input
                  id="display_name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                />
              </Field>
              <Field data-invalid={Boolean(errors.password)}>
                <FieldLabel htmlFor="password">密码</FieldLabel>
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  aria-invalid={Boolean(errors.password)}
                  required
                />
                <FieldDescription>至少 8 个字符</FieldDescription>
                <FieldError>{errors.password}</FieldError>
              </Field>
            </FieldGroup>
            <Button type="submit" disabled={submitting}>
              {submitting ? <Spinner data-icon="inline-start" /> : null}
              注册
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

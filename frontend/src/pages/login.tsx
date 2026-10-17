import { useRef, useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { useAuth } from "@/lib/auth/provider"
import { fieldErrors, notifyError } from "@/lib/errors"

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const pending = useRef(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const redirectTo = (location.state as { from?: string } | null)?.from ?? "/library"

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (pending.current) return
    pending.current = true
    setSubmitting(true)
    setErrors({})
    try {
      await login(email, password)
      navigate(redirectTo, { replace: true })
    } catch (error) {
      const fields = fieldErrors(error)
      setErrors(fields)
      if (Object.keys(fields).length === 0) {
        notifyError(error, "登录失败")
      }
    } finally {
      pending.current = false
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-muted/30 flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>登录 Paper Agent</CardTitle>
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
              <Field data-invalid={Boolean(errors.password)}>
                <FieldLabel htmlFor="password">密码</FieldLabel>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  aria-invalid={Boolean(errors.password)}
                  required
                />
                <FieldError>{errors.password}</FieldError>
              </Field>
            </FieldGroup>
            <Button type="submit" disabled={submitting}>
              {submitting ? <Spinner data-icon="inline-start" /> : null}
              登录
            </Button>
            <Button variant="link" asChild><Link to="/password-reset">忘记密码？</Link></Button>
            <p className="text-muted-foreground text-center text-sm">
              还没有账号？{" "}
              <Link className="text-foreground underline" to="/register">
                注册
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

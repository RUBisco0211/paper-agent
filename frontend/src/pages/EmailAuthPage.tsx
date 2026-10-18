import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/Field";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError, type EmailCodePurpose } from "@/lib/api";
import { useApi } from "@/components/providers/ApiProvider";
import { useAuth } from "@/components/providers/AuthProvider";
import { fieldErrors, notifySuccess } from "@/lib/errors";

type Challenge = { id: string; expiresAt: number };
type Verification = { token: string; expiresAt: number };

export function EmailAuthPage({ purpose, initialEmail }: { purpose: EmailCodePurpose; initialEmail?: string }) {
  const { api } = useApi();
  const { register, clearSession } = useAuth();
  const navigate = useNavigate();
  const isRegister = purpose === "register";
  const lockedEmail = Boolean(initialEmail);
  const [step, setStep] = useState<"email" | "code" | "password">(lockedEmail ? "code" : "email");
  const [email, setEmail] = useState(initialEmail ?? "");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [retryAt, setRetryAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [submitting, setSubmitting] = useState(false);
  const busy = useRef(false);
  const mounted = useRef(true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const retrySeconds = Math.max(0, Math.ceil((retryAt - now) / 1000));

  useEffect(() => {
    mounted.current = true;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      mounted.current = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (initialEmail) setEmail(initialEmail);
  }, [initialEmail]);

  function readChallenge(address: string) {
    const raw = window.sessionStorage.getItem(challengeKey(address));
    if (!raw) return null;
    try {
      const stored = JSON.parse(raw) as Challenge;
      if (stored.expiresAt > Date.now()) return stored;
    } catch {
      // Invalid storage is treated as missing.
    }
    window.sessionStorage.removeItem(challengeKey(address));
    return null;
  }

  useEffect(() => {
    if (!initialEmail) return;
    const until = Number(window.sessionStorage.getItem(cooldownKey(initialEmail)) ?? 0);
    if (until > Date.now()) {
      setRetryAt(until);
      setNow(Date.now());
    }
    const stored = readChallenge(initialEmail);
    if (stored) {
      setChallenge(stored);
      setStep("code");
    }
  }, [initialEmail]);

  function cooldownKey(address: string) {
    return `paper-agent:email-code-cooldown:${purpose}:${address.trim().toLowerCase()}`;
  }

  function challengeKey(address: string) {
    return `paper-agent:email-code-challenge:${purpose}:${address.trim().toLowerCase()}`;
  }

  function clearPasswords() {
    setPassword("");
    setConfirmation("");
  }

  useEffect(() => {
    if (verification && now >= verification.expiresAt) {
      setVerification(null);
      clearPasswords();
      setCode("");
      setStep("code");
      setError("邮箱验证已过期，请重新发送验证码");
    }
  }, [now, verification]);

  function changeEmail() {
    if (busy.current || lockedEmail) return;
    setStep("email");
    setChallenge(null);
    setVerification(null);
    setCode("");
    clearPasswords();
    setDisplayName("");
    setRetryAt(0);
    setErrors({});
    setError("");
  }

  async function run(action: () => Promise<void>) {
    if (busy.current) return;
    busy.current = true;
    setSubmitting(true);
    setErrors({});
    setError("");
    try {
      await action();
    } catch (cause) {
      if (!mounted.current) return;
      setErrors(fieldErrors(cause));
      // The current API uses validation_error for invalid and expired grants alike.
      const expired =
        cause instanceof ApiError &&
        (/expired|exhausted|consumed/.test(cause.code) ||
          (step === "password" &&
            /验证.*(?:失效|过期)|verification.*(?:invalid|expired)/i.test(
              cause.message,
            )));
      if (cause instanceof ApiError && cause.status === 429) {
        const details = cause.details as { retry_after?: unknown } | null;
        const delay =
          typeof details?.retry_after === "number" ? details.retry_after : 60;
        const until = Date.now() + delay * 1000;
        setRetryAt(until);
        window.sessionStorage.setItem(cooldownKey(email), String(until));
        setNow(Date.now());
        setError("发送过于频繁，请在倒计时结束后重试");
      } else if (
        expired ||
        (step === "password" &&
          cause instanceof ApiError &&
          cause.status === 401)
      ) {
        setVerification(null);
        setChallenge(null);
        clearPasswords();
        setCode("");
        setStep("code");
        setError(
          step === "password"
            ? "邮箱验证已过期，请重新发送验证码"
            : "验证码已过期，请重新发送验证码",
        );
      } else {
        setError(cause instanceof Error ? cause.message : "操作失败，请重试");
      }
    } finally {
      busy.current = false;
      if (mounted.current) setSubmitting(false);
    }
  }

  async function sendCode() {
    if (busy.current || Date.now() < retryAt) return;
    const address = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address)) {
      setErrors({ email: "请输入有效的邮箱地址" });
      return;
    }
    await run(async () => {
      const result = await api.auth.requestCode({ email: address, purpose });
      if (!mounted.current) return;
      const timestamp = Date.now();
      setEmail(address);
      const nextChallenge = {
        id: result.challenge_id,
        expiresAt: timestamp + result.expires_in * 1000,
      };
      setChallenge(nextChallenge);
      window.sessionStorage.setItem(
        challengeKey(address),
        JSON.stringify(nextChallenge),
      );
      const until = timestamp + result.retry_after * 1000;
      setRetryAt(until);
      window.sessionStorage.setItem(cooldownKey(address), String(until));
      setNow(timestamp);
      setVerification(null);
      setCode("");
      clearPasswords();
      setStep("code");
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    if (step === "email") {
      await sendCode();
      return;
    }
    if (step === "code") {
      const activeChallenge = readChallenge(email) ?? challenge;
      if (!activeChallenge) {
        setError("请先发送验证码");
        return;
      }
      if (Date.now() >= activeChallenge.expiresAt) {
        window.sessionStorage.removeItem(challengeKey(email));
        setChallenge(null);
        setError("验证码已过期，请重新发送验证码");
        return;
      }
      if (!/^\d{6}$/.test(code)) {
        setErrors({ code: "请输入 6 位数字验证码" });
        return;
      }
      setChallenge(activeChallenge);
      await run(async () => {
        const result = await api.auth.verifyCode({
          challenge_id: activeChallenge.id,
          code,
          purpose,
        });
        if (!mounted.current) return;
        setVerification({
          token: result.verification_token,
          expiresAt: Date.now() + result.expires_in * 1000,
        });
        window.sessionStorage.removeItem(challengeKey(email));
        setCode("");
        setStep("password");
      });
      return;
    }
    if (!verification || Date.now() >= verification.expiresAt) {
      setVerification(null);
      clearPasswords();
      setStep("code");
      setError("邮箱验证已过期，请重新发送验证码");
      return;
    }
    if (password.length < 8) {
      setErrors({ password: "密码至少 8 个字符" });
      return;
    }
    if (password !== confirmation) {
      setErrors({ password_confirmation: "两次输入的密码不一致" });
      return;
    }
    await run(async () => {
      const input = {
        verification_token: verification.token,
        password,
        password_confirmation: confirmation,
      };
      if (isRegister) {
        await register({
          ...input,
          display_name: displayName.trim() || undefined,
        });
      } else {
        await api.auth.resetPassword(input);
        clearSession();
      }
      if (!mounted.current) return;
      setVerification(null);
      setChallenge(null);
      clearPasswords();
      notifySuccess(isRegister ? "注册成功" : "密码已重置，请登录");
      navigate(isRegister ? "/settings" : "/login", { replace: true });
    });
  }

  return (
    <div className="bg-muted/30 flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{isRegister ? "创建账号" : "找回密码"}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => void submit(event)}
            noValidate
          >
            <FieldDescription>
              {step === "email"
                ? lockedEmail
                  ? "1 / 2 · 确认邮箱"
                  : "1 / 3 · 输入邮箱"
                : step === "code"
                  ? lockedEmail
                    ? "1 / 2 · 验证邮箱"
                    : "2 / 3 · 验证邮箱"
                  : lockedEmail
                    ? "2 / 2 · 设置密码"
                    : "3 / 3 · 设置密码"}
            </FieldDescription>
            {step !== "email" && !lockedEmail && (
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate">{email}</span>
                <Button
                  type="button"
                  variant="link"
                  disabled={submitting}
                  onClick={changeEmail}
                >
                  更换邮箱
                </Button>
              </div>
            )}
            <FieldGroup>
              {step === "email" && (
                <Field
                  data-invalid={Boolean(errors.email)}
                  data-disabled={submitting}
                >
                  <FieldLabel htmlFor="email">邮箱</FieldLabel>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) => {
                      setEmail(event.target.value);
                      setErrors({});
                      setError("");
                    }}
                    disabled={submitting}
                    readOnly={lockedEmail}
                    aria-invalid={Boolean(errors.email)}
                    aria-readonly={lockedEmail}
                    required
                  />
                  {lockedEmail && (
                    <FieldDescription>
                      将向当前登录邮箱发送验证码
                    </FieldDescription>
                  )}
                  <FieldError>{errors.email}</FieldError>
                </Field>
              )}
              {step === "code" && (
                <Field
                  data-invalid={Boolean(errors.code)}
                  data-disabled={submitting}
                >
                  <FieldLabel htmlFor="code">验证码</FieldLabel>
                  <Input
                    id="code"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    value={code}
                    onChange={(event) => {
                      setCode(event.target.value);
                      setErrors({});
                      setError("");
                    }}
                    disabled={submitting}
                    aria-invalid={Boolean(errors.code)}
                    required
                  />
                  {lockedEmail && (
                    <FieldDescription>
                      {challenge
                        ? challenge.expiresAt > now
                          ? `验证码已发送到 ${email}`
                          : "验证码已过期，请重新发送"
                        : retrySeconds > 0
                          ? `验证码已发送，请等待 ${retrySeconds} 秒后重新发送`
                          : `验证码将发送到 ${email}`}
                    </FieldDescription>
                  )}
                  <FieldDescription>
                    输入邮件中的 6 位验证码，10 分钟内有效
                  </FieldDescription>
                  <FieldError>{errors.code}</FieldError>
                </Field>
              )}
              {step === "password" && (
                <>
                  {isRegister && (
                    <Field data-disabled={submitting}>
                      <FieldLabel htmlFor="display_name">显示名称</FieldLabel>
                      <Input
                        id="display_name"
                        maxLength={120}
                        value={displayName}
                        onChange={(event) => setDisplayName(event.target.value)}
                        disabled={submitting}
                      />
                    </Field>
                  )}
                  <Field
                    data-invalid={Boolean(errors.password)}
                    data-disabled={submitting}
                  >
                    <FieldLabel htmlFor="password">密码</FieldLabel>
                    <Input
                      id="password"
                      type="password"
                      maxLength={128}
                      autoComplete="new-password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      disabled={submitting}
                      aria-invalid={Boolean(errors.password)}
                      required
                    />
                    <FieldDescription>至少 8 个字符</FieldDescription>
                    <FieldError>{errors.password}</FieldError>
                  </Field>
                  <Field
                    data-invalid={Boolean(errors.password_confirmation)}
                    data-disabled={submitting}
                  >
                    <FieldLabel htmlFor="password_confirmation">
                      确认密码
                    </FieldLabel>
                    <Input
                      id="password_confirmation"
                      type="password"
                      maxLength={128}
                      autoComplete="new-password"
                      value={confirmation}
                      onChange={(event) => setConfirmation(event.target.value)}
                      disabled={submitting}
                      aria-invalid={Boolean(errors.password_confirmation)}
                      required
                    />
                    <FieldError>{errors.password_confirmation}</FieldError>
                  </Field>
                </>
              )}
            </FieldGroup>
            {error && <FieldError>{error}</FieldError>}
            <Button
              type="submit"
              disabled={submitting || (step === "email" && retrySeconds > 0)}
            >
              {submitting && <Spinner data-icon="inline-start" />}
              {step === "email"
                ? retrySeconds > 0
                  ? `${retrySeconds} 秒后重发`
                  : "发送验证码"
                : step === "code"
                  ? "验证邮箱"
                  : isRegister
                    ? "注册"
                    : "重置密码"}
            </Button>
            {step === "code" && (
              <Button
                type="button"
                variant="outline"
                disabled={submitting || retrySeconds > 0}
                onClick={() => void sendCode()}
              >
                {retrySeconds > 0
                  ? `${retrySeconds} 秒后重发`
                  : challenge
                    ? "重新发送验证码"
                    : "发送验证码"}
              </Button>
            )}
            <Button variant="link" asChild>
              <Link to="/login">
                {isRegister ? "已有账号？登录" : "返回登录"}
              </Link>
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

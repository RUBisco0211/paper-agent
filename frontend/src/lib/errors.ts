import { toast } from "sonner"

import { ApiError } from "@/lib/api"

/**
 * One place that turns an API failure into something a user can act on.
 * The backend distinguishes input errors, permission problems, not-ready
 * resources and provider outages; the UI must not collapse them into one text.
 */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isValidation) {
      return error.message || "请检查输入内容"
    }
    if (error.status === 401) {
      if (error.code === "invalid_credentials") {
        return "邮箱或密码不正确"
      }
      return "登录态已失效，请重新登录"
    }
    if (error.status === 404) {
      return error.message || "资源不存在或无权访问"
    }
    if (error.status === 409) {
      return error.message || "当前状态不允许该操作"
    }
    if (error.isUnavailable) {
      return `${error.message || "上游服务不可用"}（可稍后重试）`
    }
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return "发生未知错误"
}

export function notifyError(error: unknown, fallback?: string): void {
  toast.error(fallback ?? "操作失败", { description: describeError(error) })
}

export function notifySuccess(message: string, description?: string): void {
  toast.success(message, { description })
}

/** Field-level messages for a form, if the API returned structured details. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !Array.isArray(error.details)) {
    return {}
  }
  const result: Record<string, string> = {}
  for (const item of error.details as Array<{ loc?: unknown[]; msg?: string }>) {
    const path = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : ""
    if (path && item.msg) {
      result[path] = item.msg
    }
  }
  return result
}

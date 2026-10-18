// @vitest-environment jsdom
import { act, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api"
import { RegisterPage } from "@/pages/RegisterPage"

const { register, requestCode, verifyCode } = vi.hoisted(() => ({ register: vi.fn(), requestCode: vi.fn(), verifyCode: vi.fn() }))
vi.mock("@/components/providers/AuthProvider", () => ({ useAuth: () => ({ register }) }))
vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api: { auth: { requestCode, verifyCode } } }) }))

beforeEach(() => {
  vi.clearAllMocks()
  requestCode.mockResolvedValue({ challenge_id: "challenge-1", retry_after: 60, expires_in: 600 })
  verifyCode.mockResolvedValue({ verification_token: "verified-1", expires_in: 600 })
  register.mockResolvedValue(undefined)
})
afterEach(() => vi.useRealTimers())
function setup() {
  render(<MemoryRouter><Routes><Route path="/" element={<RegisterPage />} /><Route path="/settings" element={<p>设置页面</p>} /></Routes></MemoryRouter>)
}
async function sendCode() {
  fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "reader@example.com" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "发送验证码" })))
}
async function verify() {
  fireEvent.change(screen.getByLabelText("验证码"), { target: { value: "123456" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "验证邮箱" })))
}
it("registration hides password inputs when the email has not been verified", async () => {
  setup()
  expect(screen.queryByLabelText("密码")).toBeNull()
  await sendCode()
  expect(requestCode).toHaveBeenCalledWith({ email: "reader@example.com", purpose: "register" })
  expect(screen.queryByLabelText("密码")).toBeNull()
  expect(screen.queryByLabelText("邮箱")).toBeNull()
})
it("registration establishes a session and opens settings when all three steps succeed", async () => {
  setup(); await sendCode(); await verify()
  expect(verifyCode).toHaveBeenCalledWith({ challenge_id: "challenge-1", code: "123456", purpose: "register" })
  expect(screen.queryByLabelText("验证码")).toBeNull()
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "password123" } })
  fireEvent.change(screen.getByLabelText("确认密码"), { target: { value: "password123" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "注册" })))
  expect(register).toHaveBeenCalledWith({ verification_token: "verified-1", password: "password123", password_confirmation: "password123", display_name: undefined })
  expect(screen.getByText("设置页面")).toBeTruthy()
})
it("registration refuses verification when the code is not six digits", async () => {
  setup(); await sendCode()
  fireEvent.change(screen.getByLabelText("验证码"), { target: { value: "12345" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "验证邮箱" })))
  expect(verifyCode).not.toHaveBeenCalled()
  expect(screen.getByText("请输入 6 位数字验证码")).toBeTruthy()
})
it("registration retains the code step when verification fails", async () => {
  verifyCode.mockRejectedValue(new ApiError(400, { code: "email_code_invalid", message: "验证码错误，请重新输入" }))
  setup(); await sendCode(); await verify()
  expect(screen.getByRole("alert").textContent).toContain("验证码错误")
  expect(screen.queryByLabelText("密码")).toBeNull()
})
it("registration clears verification state when the email is changed", async () => {
  setup(); await sendCode(); await verify()
  fireEvent.click(screen.getByRole("button", { name: "更换邮箱" }))
  expect(screen.getByLabelText("邮箱")).toBeTruthy()
  expect(screen.queryByLabelText("密码")).toBeNull()
  fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "other@example.com" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "发送验证码" })))
  expect(requestCode).toHaveBeenLastCalledWith({ email: "other@example.com", purpose: "register" })
})
it("registration blocks mismatched passwords when verification has succeeded", async () => {
  setup(); await sendCode(); await verify()
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "password123" } })
  fireEvent.change(screen.getByLabelText("确认密码"), { target: { value: "different" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "注册" })))
  expect(register).not.toHaveBeenCalled()
  expect(screen.getByText("两次输入的密码不一致")).toBeTruthy()
})
it("registration prevents duplicate sends when a request is pending", async () => {
  let resolve!: (value: unknown) => void
  requestCode.mockReturnValue(new Promise((done) => { resolve = done }))
  setup()
  fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "reader@example.com" } })
  const button = screen.getByRole("button", { name: "发送验证码" })
  fireEvent.click(button); fireEvent.click(button)
  expect(requestCode).toHaveBeenCalledTimes(1)
  await act(async () => resolve({ challenge_id: "challenge-1", retry_after: 60, expires_in: 600 }))
})
it("registration allows resending only after the server cooldown when a code was sent", async () => {
  vi.useFakeTimers(); setup(); await sendCode()
  expect((screen.getByRole("button", { name: "60 秒后重发" }) as HTMLButtonElement).disabled).toBe(true)
  await act(async () => vi.advanceTimersByTime(60000))
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "重新发送验证码" })))
  expect(requestCode).toHaveBeenCalledTimes(2)
})
it("registration requires a new code when the challenge expires", async () => {
  vi.useFakeTimers(); setup(); await sendCode()
  await act(async () => vi.advanceTimersByTime(600000))
  await verify()
  expect(verifyCode).not.toHaveBeenCalled()
  expect(screen.getByRole("alert").textContent).toContain("验证码已过期")
})
it("registration clears the password step when the verification token expires", async () => {
  vi.useFakeTimers(); setup(); await sendCode(); await verify()
  await act(async () => vi.advanceTimersByTime(600000))
  expect(screen.queryByLabelText("密码")).toBeNull()
  expect(screen.getByRole("alert").textContent).toContain("验证已过期")
})

it("registration returns to verification when the server rejects an expired grant with a validation error", async () => {
  register.mockRejectedValue(new ApiError(422, { code: "validation_error", message: "验证已失效，请重新获取验证码" }))
  setup(); await sendCode(); await verify()
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "password123" } })
  fireEvent.change(screen.getByLabelText("确认密码"), { target: { value: "password123" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "注册" })))
  expect(screen.queryByLabelText("密码")).toBeNull()
  expect(screen.getByRole("alert").textContent).toContain("验证已过期")
})

// @vitest-environment jsdom
import { act, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { PasswordResetPage } from "@/pages/password-reset"
const { requestCode, verifyCode, resetPassword, register, clearSession, currentUser } = vi.hoisted(() => ({ requestCode: vi.fn(), verifyCode: vi.fn(), resetPassword: vi.fn(), register: vi.fn(), clearSession: vi.fn(), currentUser: { value: null as { email: string } | null } }))
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ register, clearSession, user: currentUser.value }) }))
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); currentUser.value = null })
vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api: { auth: { requestCode, verifyCode, resetPassword } } }) }))
it("password reset waits for the user to send a code from the signed-in email", async () => {
  requestCode.mockResolvedValue({ challenge_id: "reset-challenge", retry_after: 60, expires_in: 600 })
  currentUser.value = { email: "reader@example.com" }
  const first = render(<MemoryRouter><Routes><Route path="/" element={<PasswordResetPage />} /></Routes></MemoryRouter>)
  expect(requestCode).not.toHaveBeenCalled()
  expect(screen.getByText("验证码将发送到 reader@example.com")).toBeTruthy()
  expect(screen.queryByLabelText("邮箱")).toBeNull()
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "发送验证码" })))
  expect(requestCode).toHaveBeenCalledWith({ email: "reader@example.com", purpose: "password_reset" })
  expect(await screen.findByText("验证码已发送到 reader@example.com")).toBeTruthy()
  expect((screen.getByRole("button", { name: "60 秒后重发" }) as HTMLButtonElement).disabled).toBe(true)
  first.unmount()
  render(<MemoryRouter><Routes><Route path="/" element={<PasswordResetPage />} /></Routes></MemoryRouter>)
  expect(requestCode).toHaveBeenCalledTimes(1)
  expect((screen.getByRole("button", { name: "60 秒后重发" }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole("button", { name: "验证邮箱" }) as HTMLButtonElement).disabled).toBe(false)
})

it("keeps verify actionable when only the cooldown survives a refresh", async () => {
  currentUser.value = { email: "reader@example.com" }
  sessionStorage.setItem(
    "paper-agent:email-code-cooldown:password_reset:reader@example.com",
    String(Date.now() + 60_000),
  )
  render(<MemoryRouter><Routes><Route path="/" element={<PasswordResetPage />} /></Routes></MemoryRouter>)
  expect(screen.getByText(/验证码已发送，请等待/)).toBeTruthy()
  const verify = screen.getByRole("button", { name: "验证邮箱" }) as HTMLButtonElement
  expect(verify.disabled).toBe(false)
  fireEvent.change(screen.getByLabelText("验证码"), { target: { value: "123456" } })
  await act(async () => fireEvent.click(verify))
  expect(screen.getByText("请先发送验证码")).toBeTruthy()
})

it("password reset returns to login without establishing a session when the three steps succeed", async () => {
  requestCode.mockResolvedValue({ challenge_id: "reset-challenge", retry_after: 60, expires_in: 600 })
  verifyCode.mockResolvedValue({ verification_token: "reset-token", expires_in: 600 })
  resetPassword.mockResolvedValue(undefined)
  render(<MemoryRouter><Routes><Route path="/" element={<PasswordResetPage />} /><Route path="/login" element={<p>登录页面</p>} /></Routes></MemoryRouter>)
  expect(screen.queryByLabelText("密码")).toBeNull()
  fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "reader@example.com" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "发送验证码" })))
  expect(requestCode).toHaveBeenCalledWith({ email: "reader@example.com", purpose: "password_reset" })
  expect(screen.queryByLabelText("密码")).toBeNull()
  fireEvent.change(screen.getByLabelText("验证码"), { target: { value: "654321" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "验证邮箱" })))
  expect(verifyCode).toHaveBeenCalledWith({ challenge_id: "reset-challenge", code: "654321", purpose: "password_reset" })
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "newpassword" } })
  fireEvent.change(screen.getByLabelText("确认密码"), { target: { value: "newpassword" } })
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "重置密码" })))
  expect(resetPassword).toHaveBeenCalledWith({ verification_token: "reset-token", password: "newpassword", password_confirmation: "newpassword" })
  expect(register).not.toHaveBeenCalled()
  expect(clearSession).toHaveBeenCalledTimes(1)
  expect(screen.getByText("登录页面")).toBeTruthy()
})

// @vitest-environment jsdom
import { act, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { PasswordResetPage } from "./password-reset"
const { requestCode, verifyCode, resetPassword, register } = vi.hoisted(() => ({ requestCode: vi.fn(), verifyCode: vi.fn(), resetPassword: vi.fn(), register: vi.fn() }))
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ register }) }))
vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api: { auth: { requestCode, verifyCode, resetPassword } } }) }))
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
  expect(screen.getByText("登录页面")).toBeTruthy()
})

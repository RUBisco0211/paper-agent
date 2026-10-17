// @vitest-environment jsdom
import { act, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { LoginPage } from "./login"
const { login } = vi.hoisted(() => ({ login: vi.fn() }))
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ login }) }))

it("login prevents duplicate submissions when the credentials request is pending", async () => {
  let resolve!: () => void
  login.mockReturnValue(new Promise<void>((done) => { resolve = done }))
  render(<MemoryRouter><LoginPage /></MemoryRouter>)
  fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "reader@example.com" } })
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "password123" } })
  const form = screen.getByRole("button", { name: "登录" }).closest("form")!
  fireEvent.submit(form); fireEvent.submit(form)
  expect(login).toHaveBeenCalledTimes(1)
  await act(async () => resolve())
})

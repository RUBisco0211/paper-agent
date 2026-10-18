import { expect, it, vi } from "vitest"
import { createApi } from "@/lib/api"

it("email authentication sends the fixed request bodies when each public endpoint is called", async () => {
  const fetchImpl = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
  const { auth } = createApi({ fetchImpl })
  await auth.requestCode({ email: "reader@example.com", purpose: "register" })
  await auth.verifyCode({ challenge_id: "challenge", code: "123456", purpose: "register" })
  await auth.register({ verification_token: "token", password: "password123", password_confirmation: "password123" })
  await auth.resetPassword({ verification_token: "token", password: "password123", password_confirmation: "password123" })
  expect(fetchImpl.mock.calls.map(([url, options]) => [url, options.method, JSON.parse(options.body)])).toEqual([
    ["/v1/auth/email-codes", "POST", { email: "reader@example.com", purpose: "register" }],
    ["/v1/auth/email-codes/verify", "POST", { challenge_id: "challenge", code: "123456", purpose: "register" }],
    ["/v1/auth/register", "POST", { verification_token: "token", password: "password123", password_confirmation: "password123" }],
    ["/v1/auth/password-reset", "POST", { verification_token: "token", password: "password123", password_confirmation: "password123" }],
  ])
})
it.each(["requestCode", "verifyCode", "resetPassword"] as const)("public auth %s does not rotate the session when the server rejects verification", async (method) => {
  const fetchImpl = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ code: "email_verification_invalid", message: "验证已过期，请重新验证邮箱" }), { status: 401 }))
  const { auth } = createApi({ fetchImpl })
  await expect(auth[method]({} as never)).rejects.toMatchObject({ status: 401 })
  expect(fetchImpl).toHaveBeenCalledTimes(1)
})

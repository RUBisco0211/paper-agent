import { expect, it } from "vitest"

import { ApiError } from "@/lib/api/errors"
import { describeError } from "@/lib/errors"

it("describeError shows a credentials error when login credentials are invalid", () => {
  const error = new ApiError(401, {
    code: "invalid_credentials",
    message: "邮箱或密码不正确",
  })

  expect(describeError(error)).toBe("邮箱或密码不正确")
})

it("describeError requests login when the session is unauthorized", () => {
  const error = new ApiError(401, { code: "unauthorized" })

  expect(describeError(error)).toBe("登录态已失效，请重新登录")
})

import { useAuth } from "@/lib/auth/provider"

import { EmailAuthPage } from "./email-auth"

export function PasswordResetPage() {
  const { user } = useAuth()
  return <EmailAuthPage purpose="password_reset" initialEmail={user?.email} />
}

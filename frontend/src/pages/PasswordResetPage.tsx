import { useAuth } from "@/components/providers/AuthProvider"

import { EmailAuthPage } from "./EmailAuthPage"

export function PasswordResetPage() {
  const { user } = useAuth()
  return <EmailAuthPage purpose="password_reset" initialEmail={user?.email} />
}

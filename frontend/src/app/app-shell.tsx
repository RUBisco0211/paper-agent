import { useQueryClient } from "@tanstack/react-query"
import {
  BookOpen,
  FolderOpen,
  LogOut,
  MessagesSquare,
  Settings,
  Sparkles,
} from "lucide-react"
import { NavLink, Outlet, useNavigate } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/lib/auth/provider"
import { cn } from "@/lib/utils"

const NAV_ITEMS = [
  { to: "/library", label: "论文库", icon: BookOpen },
  { to: "/projects", label: "项目", icon: FolderOpen },
  { to: "/sessions", label: "会话", icon: MessagesSquare },
  { to: "/settings", label: "模型设置", icon: Settings },
]

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  async function handleLogout() {
    await logout()
    queryClient.clear()
    navigate("/login", { replace: true })
  }

  return (
    <div className="bg-background flex min-h-screen">
      <aside className="border-border/60 bg-sidebar flex w-60 shrink-0 flex-col border-r">
        <div className="flex items-center gap-2 px-4 py-5">
          <Sparkles className="text-primary size-5" />
          <div>
            <p className="text-sm font-semibold">Paper Agent</p>
            <p className="text-muted-foreground text-xs">论文证据问答</p>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-2">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                )
              }
            >
              <item.icon className="size-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-border/60 border-t p-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="w-full justify-start gap-2 px-2">
                <span className="bg-primary text-primary-foreground flex size-6 items-center justify-center rounded-full text-xs">
                  {(user?.display_name || user?.email || "?").slice(0, 1).toUpperCase()}
                </span>
                <span className="truncate text-sm">{user?.email ?? "未登录"}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-56">
              <DropdownMenuLabel>{user?.display_name}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => void handleLogout()}>
                <LogOut />
                退出登录
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: React.ReactNode
}) {
  return (
    <header className="border-border/60 flex items-start justify-between gap-4 border-b px-6 py-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description ? (
          <p className="text-muted-foreground mt-1 text-sm">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  )
}

export { Badge }

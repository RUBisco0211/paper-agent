import { useQuery, useQueries } from "@tanstack/react-query"
import {
  BookOpen,
  ChevronRight,
  FolderOpen,
  LogOut,
  MessagesSquare,
  Plus,
  Settings,
  Sparkles,
  Trash2,
} from "lucide-react"
import { useState } from "react"
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"

import { queryKeys } from "@/app/query"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import type { Session } from "@/lib/api"
import { useApi } from "@/lib/api/provider"
import { useAuth } from "@/lib/auth/provider"
import { notifyError, notifySuccess } from "@/lib/errors"

const NAV_ITEMS = [
  { to: "/library", label: "论文库", icon: BookOpen },
  { to: "/projects", label: "项目", icon: FolderOpen },
  { to: "/settings", label: "设置", icon: Settings },
]

/** Sessions shown per group in the sidebar. */
const SESSIONS_PER_GROUP = 8
const SIDEBAR_PROJECT_LIMIT = 10

export function AppShell() {
  const { user, logout } = useAuth()
  const { api } = useApi()
  const navigate = useNavigate()
  const location = useLocation()
  const [deleting, setDeleting] = useState<Session | null>(null)

  const librarySessions = useQuery({
    queryKey: queryKeys.sessions({ scope: "library", sidebar: true }),
    queryFn: () => api.sessions.list({ scope: "library", limit: SESSIONS_PER_GROUP }),
  })

  const projects = useQuery({
    queryKey: queryKeys.projects({ limit: SIDEBAR_PROJECT_LIMIT }),
    queryFn: () => api.projects.list({ limit: SIDEBAR_PROJECT_LIMIT }),
  })

  const projectSessions = useQueries({
    queries: (projects.data?.items ?? []).map((project) => ({
      queryKey: queryKeys.sessions({ projectId: project.id, sidebar: true }),
      queryFn: () =>
        api.sessions.list({
          scope: "project" as const,
          project_id: project.id,
          limit: SESSIONS_PER_GROUP,
        }),
    })),
  })

  async function handleLogout() {
    await logout()
    navigate("/login", { replace: true })
  }

  async function handleDelete(session: Session) {
    try {
      await api.sessions.remove(session.id)
      notifySuccess("会话已删除")
      if (location.pathname === `/sessions/${session.id}`) {
        navigate("/sessions")
      }
    } catch (error) {
      notifyError(error)
    } finally {
      setDeleting(null)
    }
  }

  async function handleNewSession() {
    try {
      const session = await api.sessions.create({})
      navigate(`/sessions/${session.id}`)
    } catch (error) {
      notifyError(error)
    }
  }

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" asChild>
                <NavLink to="/library">
                  <span className="bg-primary text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
                    <Sparkles className="size-4" />
                  </span>
                  <span className="truncate font-semibold">Paper Agent</span>
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV_ITEMS.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild tooltip={item.label}>
                      <NavLink to={item.to}>
                        <item.icon />
                        <span>{item.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          <SidebarGroup>
            <SidebarGroupLabel>会话</SidebarGroupLabel>
            <SidebarGroupAction title="新建会话" onClick={() => void handleNewSession()}>
              <Plus />
            </SidebarGroupAction>
            <SidebarGroupContent>
              <SidebarMenu>
                <SessionGroup
                  label="个人全库"
                  to="/sessions?scope=library"
                  sessions={librarySessions.data?.items ?? []}
                  defaultOpen
                  fallbackIcon={MessagesSquare}
                  onDelete={setDeleting}
                />
                {(projects.data?.items ?? []).map((project, index) => (
                  <SessionGroup
                    key={project.id}
                    label={project.name}
                    to={`/projects/${project.id}`}
                    sessions={projectSessions[index]?.data?.items ?? []}
                    fallbackIcon={FolderOpen}
                    onDelete={setDeleting}
                  />
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton size="lg">
                    <Avatar className="size-8 rounded-lg">
                      <AvatarFallback className="rounded-lg">
                        {(user?.display_name || user?.email || "?").slice(0, 1).toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <span className="truncate">{user?.display_name || user?.email}</span>
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent side="top" align="start" className="w-56">
                  <DropdownMenuLabel className="truncate">
                    {user?.email}
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuGroup>
                    <DropdownMenuItem onSelect={() => void handleLogout()}>
                      <LogOut />
                      退出登录
                    </DropdownMenuItem>
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>

      <SidebarInset>
        {/* key 变化触发页面进入动画；侧边栏与抽屉的动画由组件自身负责 */}
        <div key={location.pathname} className="animate-page-in flex h-svh flex-col">
          <Outlet />
        </div>
      </SidebarInset>

      <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除会话「{deleting?.title ?? "未命名"}」</AlertDialogTitle>
            <AlertDialogDescription>
              会话内容与排队消息会被删除，论文库和项目不受影响。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleting && void handleDelete(deleting)}>
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SidebarProvider>
  )
}

function SessionGroup({
  label,
  to,
  sessions,
  defaultOpen = false,
  fallbackIcon: FallbackIcon,
  onDelete,
}: {
  label: string
  to: string
  sessions: Session[]
  defaultOpen?: boolean
  fallbackIcon: React.ComponentType
  onDelete: (session: Session) => void
}) {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(defaultOpen)

  return (
    <Collapsible open={open} onOpenChange={setOpen} asChild>
      <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip={label}>
          <NavLink to={to}>
            <FallbackIcon />
            <span className="truncate">{label}</span>
          </NavLink>
        </SidebarMenuButton>
        {sessions.length > 0 ? (
          <>
            <CollapsibleTrigger asChild>
              <SidebarMenuAction
                className="data-[state=open]:rotate-90"
                title={open ? "收起" : "展开"}
              >
                <ChevronRight />
              </SidebarMenuAction>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <SidebarMenuSub>
                {sessions.map((session) => (
                  <SidebarMenuSubItem key={session.id}>
                    <SidebarMenuSubButton
                      asChild
                      isActive={pathname === `/sessions/${session.id}`}
                    >
                      <NavLink to={`/sessions/${session.id}`}>
                        <span className="truncate">{session.title ?? "未命名会话"}</span>
                      </NavLink>
                    </SidebarMenuSubButton>
                    <SidebarMenuAction
                      title="删除会话"
                      onClick={(event) => {
                        event.preventDefault()
                        onDelete(session)
                      }}
                    >
                      <Trash2 />
                    </SidebarMenuAction>
                  </SidebarMenuSubItem>
                ))}
              </SidebarMenuSub>
            </CollapsibleContent>
          </>
        ) : null}
      </SidebarMenuItem>
    </Collapsible>
  )
}

export function PageHeader({
  title,
  actions,
  leading,
}: {
  title: string
  actions?: React.ReactNode
  leading?: React.ReactNode
}) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b px-4">
      <div className="flex min-w-0 items-center gap-2">
        <SidebarTrigger className="-ml-1" />
        {leading}
        <h1 className="truncate text-base font-medium">{title}</h1>
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  )
}

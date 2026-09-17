import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  BookOpen,
  ChevronRight,
  FolderOpen,
  LogOut,
  MoreHorizontal,
  Plus,
  Settings,
  Sparkles,
  Trash2,
} from "lucide-react"
import { useCallback, useState } from "react"
import { cn } from "cn"
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"

import { queryKeys } from "@/app/query"
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
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  Collapsible,
  CollapsibleContent,
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
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"
import type { Session } from "@/lib/api"
import { useApi } from "@/lib/api/provider"
import { useAuth } from "@/lib/auth/provider"
import { notifyError, notifySuccess } from "@/lib/errors"
import { useSidebarWidth } from "@/lib/hooks/use-sidebar-width"

const NAV_ITEMS = [
  { to: "/library", label: "文献库", icon: BookOpen },
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
  const queryClient = useQueryClient()
  const { width, setWidth } = useSidebarWidth()
  const [deleting, setDeleting] = useState<Session | null>(null)
  const [deletingProject, setDeletingProject] = useState<{ id: string; name: string } | null>(
    null,
  )

  const librarySessions = useQuery({
    queryKey: queryKeys.sessions({ scope: "library", sidebar: true }),
    queryFn: () => api.sessions.list({ scope: "library", limit: SESSIONS_PER_GROUP }),
  })

  // 单篇文献会话一次取回，按文献分组显示
  const paperSessions = useQuery({
    queryKey: queryKeys.sessions({ scope: "paper", sidebar: true }),
    queryFn: () => api.sessions.list({ scope: "paper", limit: 100 }),
  })

  const papers = useQuery({
    queryKey: queryKeys.papers({ sidebar: true }),
    queryFn: () => api.library.list({ limit: 200 }),
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

  const paperTitles = new Map(
    (papers.data?.items ?? []).map((paper) => [
      paper.id,
      paper.title ?? paper.original_filename ?? "未命名文献",
    ]),
  )

  const paperGroups = new Map<string, Session[]>()
  for (const session of paperSessions.data?.items ?? []) {
    if (!session.paper_id) {
      continue
    }
    const group = paperGroups.get(session.paper_id) ?? []
    group.push(session)
    paperGroups.set(session.paper_id, group)
  }

  const openSession = useCallback(
    async (input: { project_id?: string; paper_id?: string; title?: string }) => {
      try {
        const session = await api.sessions.create(input)
        void queryClient.invalidateQueries({ queryKey: ["sessions"] })
        navigate(`/sessions/${session.id}`)
      } catch (error) {
        notifyError(error)
      }
    },
    [api, navigate, queryClient],
  )

  async function handleLogout() {
    await logout()
    navigate("/login", { replace: true })
  }

  async function handleDelete(session: Session) {
    try {
      await api.sessions.remove(session.id)
      notifySuccess("会话已删除")
      void queryClient.invalidateQueries({ queryKey: ["sessions"] })
      if (location.pathname === `/sessions/${session.id}`) {
        navigate("/library")
      }
    } catch (error) {
      notifyError(error)
    } finally {
      setDeleting(null)
    }
  }

  return (
    <SidebarProvider style={{ "--sidebar-width": `${width}px` } as React.CSSProperties}>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <div className="flex items-center gap-1">
            <SidebarLogo />
            <SidebarTrigger className="ml-auto group-data-[collapsible=icon]:hidden" />
          </div>
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
            <SidebarGroupContent>
              <SidebarMenu>
                <SessionGroup
                  label="全局"
                  sessions={librarySessions.data?.items ?? []}
                  defaultOpen
                  onCreate={() => void openSession({})}
                  actions={[{ label: "新建会话", icon: Plus, onSelect: () => void openSession({}) }]}
                />
                {(projects.data?.items ?? []).map((project, index) => (
                  <SessionGroup
                    key={project.id}
                    label={project.name}
                    icon={FolderOpen}
                    sessions={projectSessions[index]?.data?.items ?? []}
                    onCreate={() =>
                      void openSession({ project_id: project.id, title: project.name })
                    }
                    actions={[
                      {
                        label: "查看详情",
                        onSelect: () => navigate(`/projects/${project.id}`),
                      },
                      {
                        label: "添加文献",
                        onSelect: () => navigate(`/projects/${project.id}?add=1`),
                      },
                      {
                        label: "新建会话",
                        onSelect: () =>
                          void openSession({ project_id: project.id, title: project.name }),
                      },
                    ]}
                    destructiveAction={{
                      label: "删除项目",
                      onSelect: () => setDeletingProject({ id: project.id, name: project.name }),
                    }}
                  />
                ))}
                {[...paperGroups.entries()].map(([paperId, sessions]) => (
                  <SessionGroup
                    key={paperId}
                    label={paperTitles.get(paperId) ?? "单篇文献"}
                    icon={BookOpen}
                    sessions={sessions}
                    onCreate={() => void openSession({ paper_id: paperId })}
                    actions={[
                      {
                        label: "新建会话",
                        onSelect: () => void openSession({ paper_id: paperId }),
                      },
                    ]}
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
                  <DropdownMenuLabel className="truncate">{user?.email}</DropdownMenuLabel>
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
        <SidebarResizeHandle width={width} onWidthChange={setWidth} />
      </Sidebar>

      <SidebarInset>
        {/* key 变化触发页面进入动画；侧边栏与抽屉的动画由组件自身负责 */}
        <div key={location.pathname} className="animate-page-in flex h-svh flex-col">
          <Outlet />
        </div>
      </SidebarInset>

      <AlertDialog
        open={Boolean(deletingProject)}
        onOpenChange={(open) => !open && setDeletingProject(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除项目「{deletingProject?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              项目中的会话会一并删除，文献库不受影响。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deletingProject && void handleDeleteProject(deletingProject.id)}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除会话「{deleting?.title ?? "未命名"}」？</AlertDialogTitle>
            <AlertDialogDescription>
              会话内容会被删除，文献库和项目不受影响。
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

  async function handleDeleteProject(projectId: string) {
    try {
      await api.projects.remove(projectId)
      notifySuccess("项目已删除")
      void queryClient.invalidateQueries({ queryKey: ["projects"] })
      void queryClient.invalidateQueries({ queryKey: ["sessions"] })
      if (location.pathname.startsWith(`/projects/${projectId}`)) {
        navigate("/projects")
      }
    } catch (error) {
      notifyError(error)
    } finally {
      setDeletingProject(null)
    }
  }
}

/** 折叠时只显示 logo，点击 logo 展开；展开时点击回到文献库。 */
function SidebarLogo() {
  const { state, setOpen } = useSidebar()
  const collapsed = state === "collapsed"

  const handleClick = (event: React.MouseEvent) => {
    if (collapsed) {
      event.preventDefault()
      setOpen(true)
    }
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton size="lg" asChild tooltip="Paper Agent">
          <NavLink to="/library" onClick={handleClick}>
            <span className="bg-primary text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
              <Sparkles />
            </span>
            <span className="truncate font-semibold">Paper Agent</span>
          </NavLink>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

type GroupAction = {
  label: string
  icon?: React.ComponentType
  onSelect: () => void
}

/**
 * 一个会话分组（全局 / 项目 / 单篇文献）。
 * 点击整行切换展开折叠；三点菜单承载该分组上的操作。
 */
function SessionGroup({
  label,
  icon: Icon,
  sessions,
  defaultOpen = false,
  onCreate,
  actions = [],
  destructiveAction,
}: {
  label: string
  icon?: React.ComponentType
  sessions: Session[]
  defaultOpen?: boolean
  onCreate: () => void
  actions?: GroupAction[]
  destructiveAction?: GroupAction
}) {
  const location = useLocation()
  const [open, setOpen] = useState(defaultOpen)
  const menuActions = actions.length > 0 ? actions : [{ label: "新建会话", icon: Plus, onSelect: onCreate }]

  return (
    <Collapsible open={open} onOpenChange={setOpen} asChild>
      <SidebarMenuItem>
        <SidebarMenuButton tooltip={label} onClick={() => setOpen((value) => !value)}>
          {Icon ? <Icon /> : <FolderOpen />}
          <span className="truncate">{label}</span>
          <ChevronRight
            className={cn(
              "ml-auto transition-transform group-data-[collapsible=icon]:hidden",
              open && "rotate-90",
            )}
          />
        </SidebarMenuButton>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuAction showOnHover title={`${label} 操作`}>
              <MoreHorizontal />
            </SidebarMenuAction>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="start" className="w-44">
            <DropdownMenuGroup>
              {menuActions.map((action) => (
                <DropdownMenuItem key={action.label} onSelect={action.onSelect}>
                  {action.icon ? <action.icon /> : null}
                  {action.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
            {destructiveAction ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuGroup>
                  <DropdownMenuItem
                    variant="destructive"
                    onSelect={destructiveAction.onSelect}
                  >
                    <Trash2 />
                    {destructiveAction.label}
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>

        <CollapsibleContent>
          <SidebarMenuSub>
            {sessions.map((session) => (
              <SidebarMenuSubItem key={session.id}>
                <SidebarMenuSubButton
                  asChild
                  isActive={location.pathname === `/sessions/${session.id}`}
                >
                  <NavLink to={`/sessions/${session.id}`}>
                    <span className="truncate">{session.title ?? "未命名会话"}</span>
                  </NavLink>
                </SidebarMenuSubButton>
              </SidebarMenuSubItem>
            ))}
            {sessions.length === 0 ? (
              <SidebarMenuSubItem>
                <span className="text-muted-foreground px-2 py-1 text-xs">暂无会话</span>
              </SidebarMenuSubItem>
            ) : null}
          </SidebarMenuSub>
        </CollapsibleContent>
      </SidebarMenuItem>
    </Collapsible>
  )
}

/** 拖拽调整侧边栏宽度（宽度是布局偏好，持久化在本地）。 */
function SidebarResizeHandle({
  width,
  onWidthChange,
}: {
  width: number
  onWidthChange: (width: number) => void
}) {
  const { state } = useSidebar()

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    const startX = event.clientX
    const startWidth = width
    const target = event.currentTarget
    target.setPointerCapture(event.pointerId)

    const handlePointerMove = (moveEvent: PointerEvent) => {
      onWidthChange(startWidth + (moveEvent.clientX - startX))
    }
    const handlePointerUp = () => {
      target.releasePointerCapture(event.pointerId)
      target.removeEventListener("pointermove", handlePointerMove)
      target.removeEventListener("pointerup", handlePointerUp)
    }
    target.addEventListener("pointermove", handlePointerMove)
    target.addEventListener("pointerup", handlePointerUp)
  }

  if (state === "collapsed") {
    return null
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="调整侧边栏宽度"
      onPointerDown={handlePointerDown}
      className="hover:bg-sidebar-border absolute inset-y-0 -right-1 z-20 hidden w-2 cursor-col-resize sm:block"
    />
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
        {leading}
        <h1 className="truncate text-base font-medium">{title}</h1>
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  )
}

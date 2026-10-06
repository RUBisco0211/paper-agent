import { useQuery, useQueryClient } from "@tanstack/react-query"
import { BookOpen, ChevronDown, FolderOpen, KeyRound, LogOut, MoreHorizontal, Plus } from "lucide-react"
import { useState } from "react"
import { NavLink, useLocation, useNavigate } from "react-router-dom"

import { useApi } from "@/lib/api/provider"
import { createBoundSession, deleteBoundSession, listBoundSessions, type BoundSession } from "@/lib/agent-sessions"
import { useAuth } from "@/lib/auth/provider"
import { sessionApi } from "@upstream/api/session"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@upstream/components/ui/collapsible"
import { Button } from "@upstream/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@upstream/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@upstream/components/ui/dropdown-menu"
import { Input } from "@upstream/components/ui/input"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@upstream/components/ui/sidebar"

const items = [
  { to: "/library", label: "文献库", icon: BookOpen },
  { to: "/projects", label: "项目", icon: FolderOpen },
  { to: "/settings", label: "模型设置", icon: KeyRound },
]

function SessionRows({ sessions, onRename, onDelete }: { sessions: BoundSession[]; onRename: (session: BoundSession) => void; onDelete: (session: BoundSession) => void }) {
  return sessions.map((item) => (
    <SidebarMenuItem key={item.session.session.id}>
      <SidebarMenuButton asChild tooltip={item.session.session.config.name || "会话"}>
        <NavLink to={`/chat/${item.agentId}/${item.session.session.id}`}>
          <span className="truncate">{item.session.session.config.name || "新会话"}</span>
        </NavLink>
      </SidebarMenuButton>
      <DropdownMenu>
        <DropdownMenuTrigger asChild><SidebarMenuAction showOnHover aria-label="会话操作"><MoreHorizontal /></SidebarMenuAction></DropdownMenuTrigger>
        <DropdownMenuContent side="right" align="start">
          <DropdownMenuItem onSelect={() => onRename(item)}>重命名</DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => onDelete(item)}>删除会话</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  ))
}

export function AppSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { logout } = useAuth()
  const { api } = useApi()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState("")
  const [renaming, setRenaming] = useState<BoundSession | null>(null)
  const [name, setName] = useState("")
  const [savingName, setSavingName] = useState(false)
  const [deleting, setDeleting] = useState<BoundSession | null>(null)
  const [deleteError, setDeleteError] = useState("")
  const [deletingNow, setDeletingNow] = useState(false)
  const projects = useQuery({
    queryKey: ["sidebar-projects"],
    queryFn: () => api.projects.list({ limit: 100 }),
  })
  const sessions = useQuery({
    queryKey: ["bound-sessions"],
    queryFn: () => listBoundSessions(api),
  })

  async function create(projectId?: string) {
    setCreating(true)
    setError("")
    try {
      const result = await createBoundSession(api, { projectId })
      await queryClient.invalidateQueries({ queryKey: ["bound-sessions"] })
      navigate(`/chat/${result.agentId}/${result.sessionId}`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建会话失败")
    } finally {
      setCreating(false)
    }
  }

  function beginRename(session: BoundSession) {
    setRenaming(session)
    setName(session.session.session.config.name || "")
    setError("")
  }

  async function rename() {
    if (!renaming || !name.trim()) return
    setSavingName(true)
    setError("")
    try {
      await sessionApi.update(renaming.session.session.id, renaming.agentId, { name: name.trim() })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["bound-sessions"] }),
        queryClient.invalidateQueries({ queryKey: ["agent-sessions", renaming.agentId] }),
      ])
      setRenaming(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "重命名失败，请重试")
    } finally {
      setSavingName(false)
    }
  }

  async function remove() {
    if (!deleting) return
    setDeletingNow(true)
    setDeleteError("")
    try {
      await deleteBoundSession(api, {
        agentId: deleting.agentId,
        sessionId: deleting.session.session.id,
      })
      await queryClient.invalidateQueries({ queryKey: ["bound-sessions"] })
      if (location.pathname === `/chat/${deleting.agentId}/${deleting.session.session.id}`) {
        navigate("/library", { replace: true })
      }
      setDeleting(null)
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : "删除失败，请重试")
    } finally {
      setDeletingNow(false)
    }
  }

  const all = sessions.data ?? []
  const globalSessions = all.filter((item) => item.binding.project_id === null)

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-5 font-semibold tracking-tight">Paper Agent</SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map(({ to, label, icon: Icon }) => (
                <SidebarMenuItem key={to}>
                  <SidebarMenuButton asChild tooltip={label}>
                    <NavLink to={to}><Icon />{label}</NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel className="flex items-center justify-between">全局
            <button type="button" aria-label="新建全局会话" disabled={creating} onClick={() => void create()}><Plus className="size-4" /></button>
          </SidebarGroupLabel>
          <SidebarGroupContent><SidebarMenu><SessionRows sessions={globalSessions} onRename={beginRename} onDelete={setDeleting} /></SidebarMenu></SidebarGroupContent>
        </SidebarGroup>
        {(projects.data?.items ?? []).map((project) => (
          <Collapsible key={project.id} defaultOpen>
            <SidebarGroup>
              <SidebarGroupLabel className="flex items-center justify-between">
                <CollapsibleTrigger className="flex min-w-0 items-center gap-1 truncate"><ChevronDown className="size-3.5" />{project.name}</CollapsibleTrigger>
                <button type="button" aria-label={`在${project.name}中新建会话`} disabled={creating} onClick={() => void create(project.id)}><Plus className="size-4" /></button>
              </SidebarGroupLabel>
              <CollapsibleContent><SidebarGroupContent><SidebarMenu>
                <SessionRows sessions={all.filter((item) => item.binding.project_id === project.id)} onRename={beginRename} onDelete={setDeleting} />
              </SidebarMenu></SidebarGroupContent></CollapsibleContent>
            </SidebarGroup>
          </Collapsible>
        ))}
        {error && <p role="alert" className="px-4 text-xs text-destructive">{error}</p>}
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu><SidebarMenuItem>
          <SidebarMenuButton onClick={() => void logout().then(() => navigate("/login", { replace: true }))}>
            <LogOut />退出登录
          </SidebarMenuButton>
        </SidebarMenuItem></SidebarMenu>
      </SidebarFooter>
      <Dialog open={Boolean(renaming)} onOpenChange={(open) => !open && setRenaming(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>重命名会话</DialogTitle></DialogHeader>
          <form onSubmit={(event) => { event.preventDefault(); void rename() }} className="space-y-4">
            <Input aria-label="会话名称" value={name} onChange={(event) => setName(event.target.value)} autoFocus />
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <DialogFooter><Button type="submit" disabled={!name.trim() || savingName}>保存</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(deleting)} onOpenChange={(open) => { if (!open && !deletingNow) { setDeleting(null); setDeleteError("") } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除会话</DialogTitle>
            <DialogDescription>删除“{deleting?.session.session.config.name || "新会话"}”及其历史记录？此操作无法撤销。</DialogDescription>
          </DialogHeader>
          {deleteError && <p role="alert" className="text-sm text-destructive">{deleteError}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={deletingNow} onClick={() => setDeleting(null)}>取消</Button>
            <Button type="button" variant="destructive" disabled={deletingNow} onClick={() => void remove()}>{deletingNow ? "删除中…" : "删除"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sidebar>
  )
}

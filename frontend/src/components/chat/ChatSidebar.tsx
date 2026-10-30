import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { NavLink, useLocation, useNavigate } from "react-router-dom"

import { useApi } from "@/components/providers/ApiProvider"
import { CreateProjectDialog } from "@/components/projects/CreateProjectDialog"
import { AddPapersDialog } from "@/components/projects/AddPapersDialog"
import { deleteBoundSession, deleteProjectWithSessions, listBoundSessions } from "@/lib/agentSessions"
import type { BoundSession } from "@/types/session"
import { sessionApi } from "@/lib/api/agentscope/session"
import { chatPath } from "./chatView"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/Collapsible"
import { Button } from "@/components/ui/Button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/Dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/DropdownMenu"
import { Input } from "@/components/ui/Input"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/Sidebar"

function SessionRows({ sessions, activePath, onRename, onDelete }: { sessions: BoundSession[]; activePath: string; onRename: (session: BoundSession) => void; onDelete: (session: BoundSession) => void }) {
  return sessions.map((item) => (
    <SidebarMenuItem key={item.session.session.id}>
      <SidebarMenuButton asChild isActive={chatPath(item) === activePath} tooltip={item.session.session.config.name || "会话"}>
        <NavLink to={chatPath(item)}>
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

export function ChatSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { api } = useApi()
  const queryClient = useQueryClient()
  const [error, setError] = useState("")
  const [renaming, setRenaming] = useState<BoundSession | null>(null)
  const [name, setName] = useState("")
  const [savingName, setSavingName] = useState(false)
  const [deleting, setDeleting] = useState<BoundSession | null>(null)
  const [deleteError, setDeleteError] = useState("")
  const [deletingNow, setDeletingNow] = useState(false)
  const [projectToRename, setProjectToRename] = useState<{ id: string; name: string } | null>(null)
  const [projectName, setProjectName] = useState("")
  const [projectToDelete, setProjectToDelete] = useState<{ id: string; name: string } | null>(null)
  const [projectBusy, setProjectBusy] = useState(false)
  const [addPapersTo, setAddPapersTo] = useState<string | null>(null)
  const projects = useQuery({
    queryKey: ["sidebar-projects"],
    queryFn: () => api.projects.list({ limit: 100 }),
  })
  const sessions = useQuery({
    queryKey: ["bound-sessions"],
    queryFn: () => listBoundSessions(api),
  })
  const targetPapers = useQuery({
    queryKey: ["project-papers", addPapersTo],
    queryFn: () => api.projects.papers(addPapersTo!, { limit: 200 }),
    enabled: Boolean(addPapersTo),
  })

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
        navigate("/chat", { replace: true })
      }
      setDeleting(null)
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : "删除失败，请重试")
    } finally {
      setDeletingNow(false)
    }
  }

  async function renameProject() {
    if (!projectToRename || !projectName.trim()) return
    setProjectBusy(true)
    setError("")
    try {
      await api.projects.rename(projectToRename.id, { name: projectName.trim() })
      await queryClient.invalidateQueries({ queryKey: ["sidebar-projects"] })
      void queryClient.invalidateQueries({ queryKey: ["calendar-projects"] })
      await queryClient.invalidateQueries({ queryKey: ["project", projectToRename.id] })
      setProjectToRename(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "重命名失败")
    } finally {
      setProjectBusy(false)
    }
  }

  async function removeProject() {
    if (!projectToDelete) return
    setProjectBusy(true)
    setError("")
    try {
      await deleteProjectWithSessions(api, projectToDelete.id)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sidebar-projects"] }),
        queryClient.invalidateQueries({ queryKey: ["calendar-projects"] }),
        queryClient.invalidateQueries({ queryKey: ["bound-sessions"] }),
      ])
      setProjectToDelete(null)
      navigate("/chat", { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除失败")
    } finally {
      setProjectBusy(false)
    }
  }

  const all = sessions.data ?? []
  const globalSessions = all.filter((item) => item.binding.project_id === null)

  return (
    <Sidebar collapsible="none" className="w-(--chat-sidebar-width) border-r">
      <SidebarHeader className="h-(--app-toolbar-height) justify-center px-4 font-semibold tracking-tight">对话</SidebarHeader>
      <SidebarContent>
        <SidebarGroup className="pt-0">
          <CreateProjectDialog trigger={<Button variant="ghost" className="w-full justify-start gap-2" aria-label="新建项目"><Plus className="size-4" />新建项目</Button>} onCreated={(id) => { void queryClient.invalidateQueries({ queryKey: ["sidebar-projects"] }); void queryClient.invalidateQueries({ queryKey: ["calendar-projects"] }); navigate(`/chat/project/${id}`) }} />
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel className="flex items-center justify-between">全局
            <button type="button" aria-label="新建全局会话" onClick={() => navigate("/chat/new", { state: { initialProjectId: null } })}><Plus className="size-4" /></button>
          </SidebarGroupLabel>
          <SidebarGroupContent><SidebarMenu><SessionRows sessions={globalSessions} activePath={location.pathname} onRename={beginRename} onDelete={setDeleting} /></SidebarMenu></SidebarGroupContent>
        </SidebarGroup>
        {(projects.data?.items ?? []).map((project) => (
          <Collapsible key={project.id} defaultOpen>
            <SidebarGroup>
              <SidebarGroupLabel className="flex items-center justify-between">
                <CollapsibleTrigger className="flex min-w-0 items-center gap-1 truncate"><ChevronDown className="size-3.5" />{project.name}</CollapsibleTrigger>
                <span className="flex items-center gap-1">
                  <button type="button" aria-label={`在${project.name}中新建会话`} onClick={() => navigate("/chat/new", { state: { initialProjectId: project.id } })}><Plus className="size-4" /></button>
                  <DropdownMenu><DropdownMenuTrigger asChild><button type="button" aria-label={`${project.name}操作`}><MoreHorizontal className="size-4" /></button></DropdownMenuTrigger>
                    <DropdownMenuContent side="right" align="start">
                      <DropdownMenuItem onSelect={() => setAddPapersTo(project.id)}><Plus />添加文献</DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => { setProjectToRename(project); setProjectName(project.name); setError("") }}><Pencil />重命名</DropdownMenuItem>
                      <DropdownMenuItem variant="destructive" onSelect={() => { setProjectToDelete(project); setError("") }}><Trash2 />删除项目</DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </span>
              </SidebarGroupLabel>
              <CollapsibleContent><SidebarGroupContent><SidebarMenu>
                <SessionRows sessions={all.filter((item) => item.binding.project_id === project.id)} activePath={location.pathname} onRename={beginRename} onDelete={setDeleting} />
              </SidebarMenu></SidebarGroupContent></CollapsibleContent>
            </SidebarGroup>
          </Collapsible>
        ))}
        {error && <p role="alert" className="px-4 text-xs text-destructive">{error}</p>}
      </SidebarContent>
      {addPapersTo && <AddPapersDialog projectId={addPapersTo} existingPaperIds={(targetPapers.data?.items ?? []).map((item) => item.id)} trigger={<button type="button" className="hidden" tabIndex={-1} aria-hidden="true" />} open onOpenChange={(open) => !open && setAddPapersTo(null)} />}
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
      <Dialog open={Boolean(projectToRename)} onOpenChange={(open) => !open && !projectBusy && setProjectToRename(null)}>
        <DialogContent><DialogHeader><DialogTitle>重命名项目</DialogTitle></DialogHeader>
          <form onSubmit={(event) => { event.preventDefault(); void renameProject() }} className="space-y-4">
            <Input aria-label="项目名称" value={projectName} onChange={(event) => setProjectName(event.target.value)} />
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <DialogFooter><Button type="submit" disabled={!projectName.trim() || projectBusy}>保存</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(projectToDelete)} onOpenChange={(open) => !open && !projectBusy && setProjectToDelete(null)}>
        <DialogContent><DialogHeader><DialogTitle>删除项目</DialogTitle><DialogDescription>删除“{projectToDelete?.name}”及其中会话？文献库中的文献会保留。</DialogDescription></DialogHeader>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <DialogFooter><Button variant="outline" disabled={projectBusy} onClick={() => setProjectToDelete(null)}>取消</Button><Button variant="destructive" disabled={projectBusy} onClick={() => void removeProject()}>删除</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Sidebar>
  )
}

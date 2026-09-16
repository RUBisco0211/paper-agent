import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MessagesSquare, Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"

import { PageHeader } from "@/app/app-shell"
import { queryKeys } from "@/app/query"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
  Empty,
  EmptyContent,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { Session } from "@/lib/api"
import { useApi } from "@/lib/api/provider"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"

export function SessionsPage() {
  const { api } = useApi()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  // 侧边栏的“个人全库 / 某项目”链接通过查询参数指定初始范围。
  const [searchParams, setSearchParams] = useSearchParams()
  const [scope, setScope] = useState<"library" | "project">(
    searchParams.get("scope") === "project" || searchParams.get("project_id")
      ? "project"
      : "library",
  )
  const [projectId, setProjectId] = useState<string>(
    searchParams.get("project_id") ?? "",
  )
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState("")
  const [deleting, setDeleting] = useState<Session | null>(null)

  const projects = useQuery({
    queryKey: queryKeys.projects({ limit: 100 }),
    queryFn: () => api.projects.list({ limit: 100 }),
    enabled: scope === "project" || creating,
  })

  const sessions = useQuery({
    queryKey: queryKeys.sessions({ scope, projectId }),
    queryFn: () =>
      api.sessions.list({
        limit: 100,
        scope: scope === "project" ? "project" : "library",
        project_id: scope === "project" && projectId ? projectId : undefined,
      }),
    enabled: scope === "library" || Boolean(projectId),
  })

  const create = useMutation({
    mutationFn: () =>
      api.sessions.create({
        title: newTitle.trim() || undefined,
        project_id: scope === "project" && projectId ? projectId : undefined,
      }),
    onSuccess: (session) => {
      setCreating(false)
      setNewTitle("")
      void queryClient.invalidateQueries({ queryKey: ["sessions"] })
      navigate(`/sessions/${session.id}`)
    },
    onError: (error) => notifyError(error, "创建会话失败"),
  })

  const remove = useMutation({
    mutationFn: (sessionId: string) => api.sessions.remove(sessionId),
    onSuccess: () => {
      notifySuccess("会话已删除")
      setDeleting(null)
      void queryClient.invalidateQueries({ queryKey: ["sessions"] })
    },
    onError: (error) => notifyError(error, "删除失败"),
  })

  function updateScope(next: "library" | "project", nextProjectId = "") {
    setScope(next)
    setProjectId(nextProjectId)
    const params = new URLSearchParams()
    if (next === "project") {
      params.set("scope", "project")
      if (nextProjectId) {
        params.set("project_id", nextProjectId)
      }
    }
    setSearchParams(params, { replace: true })
  }

  const items = sessions.data?.items ?? []

  return (
    <>
      <PageHeader
        title="会话"
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus data-icon="inline-start" />
            新建会话
          </Button>
        }
      />

      <div className="flex flex-1 flex-col gap-4 p-6">
        <div className="flex items-center gap-3">
          <ToggleGroup
            type="single"
            variant="outline"
            value={scope}
            onValueChange={(value) => {
              if (value) {
                updateScope(value as "library" | "project")
              }
            }}
          >
            <ToggleGroupItem value="library">个人全库</ToggleGroupItem>
            <ToggleGroupItem value="project">项目范围</ToggleGroupItem>
          </ToggleGroup>
          {scope === "project" ? (
            <Select
              value={projectId}
              onValueChange={(value) => updateScope("project", value)}
            >
              <SelectTrigger className="w-56">
                <SelectValue placeholder="选择项目" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {projects.data?.items.map((project) => (
                    <SelectItem key={project.id} value={project.id}>
                      {project.name}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          ) : null}
        </div>

        {sessions.isError ? (
          <Alert variant="destructive">
            <AlertTitle>加载失败</AlertTitle>
            <AlertDescription>{describeError(sessions.error)}</AlertDescription>
          </Alert>
        ) : null}

        {sessions.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : items.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <MessagesSquare />
              </EmptyMedia>
              <EmptyTitle>还没有会话</EmptyTitle>
            </EmptyHeader>
            <EmptyContent>
              <Button onClick={() => setCreating(true)}>
                <Plus data-icon="inline-start" />
                新建会话
              </Button>
            </EmptyContent>
          </Empty>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>标题</TableHead>
                  <TableHead>范围</TableHead>
                  <TableHead>待发送</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((session) => (
                  <TableRow key={session.id}>
                    <TableCell>
                      <Link
                        className="font-medium underline-offset-4 hover:underline"
                        to={`/sessions/${session.id}`}
                      >
                        {session.title ?? "未命名会话"}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {session.scope === "project" ? (
                        <Badge variant="outline">项目</Badge>
                      ) : (
                        <Badge variant="outline">个人全库</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {session.pending.steering + session.pending.follow_up > 0 ? (
                        <Badge variant="secondary">
                          {session.pending.steering + session.pending.follow_up}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {new Date(session.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setDeleting(session)}
                      >
                        <Trash2 data-icon="inline-start" />
                        删除
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>新建会话</DialogTitle>
          </DialogHeader>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              create.mutate()
            }}
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="session-title">标题（可选）</Label>
              <Input
                id="session-title"
                value={newTitle}
                onChange={(event) => setNewTitle(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="session-scope">范围</Label>
              <Select
                value={scope === "project" ? projectId || "none" : "library"}
                onValueChange={(value) =>
                  updateScope(value === "library" ? "library" : "project", value === "library" ? "" : value)
                }
              >
                <SelectTrigger id="session-scope" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="library">个人全库</SelectItem>
                    {projects.data?.items.map((project) => (
                      <SelectItem key={project.id} value={project.id}>
                        项目：{project.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button
                type="submit"
                disabled={create.isPending || (scope === "project" && !projectId)}
              >
                创建
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除会话「{deleting?.title ?? "未命名"}」？</AlertDialogTitle>
            <AlertDialogDescription>
              会话内容会被删除，论文库和项目不受影响。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleting && remove.mutate(deleting.id)}>
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

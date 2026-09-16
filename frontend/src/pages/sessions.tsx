import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MessagesSquare, Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { PageHeader } from "@/app/app-shell"
import { queryKeys } from "@/app/query"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
  const [scope, setScope] = useState<"library" | "project">("library")
  const [projectId, setProjectId] = useState<string>("")
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

  const items = sessions.data?.items ?? []

  return (
    <>
      <PageHeader
        title="会话"
        description="个人全库会话覆盖整个论文库；项目会话只覆盖该项目论文，范围创建后不可修改。"
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" />
            新建会话
          </Button>
        }
      />

      <div className="flex flex-1 flex-col gap-4 p-6">
        <div className="flex items-center gap-3">
          <Select
            value={scope}
            onValueChange={(value) => {
              setScope(value as "library" | "project")
              setProjectId("")
            }}
          >
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="library">个人全库</SelectItem>
              <SelectItem value="project">项目范围</SelectItem>
            </SelectContent>
          </Select>
          {scope === "project" ? (
            <Select value={projectId} onValueChange={setProjectId}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder="选择项目" />
              </SelectTrigger>
              <SelectContent>
                {projects.data?.items.map((project) => (
                  <SelectItem key={project.id} value={project.id}>
                    {project.name}
                  </SelectItem>
                ))}
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
          <Card>
            <CardContent className="text-muted-foreground flex flex-col items-center gap-2 py-12 text-sm">
              <MessagesSquare className="size-5" />
              <p>没有会话</p>
              <p>新建会话后即可在授权范围内提问。</p>
            </CardContent>
          </Card>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>标题</TableHead>
                  <TableHead>范围</TableHead>
                  <TableHead>排队</TableHead>
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
                        <Trash2 className="size-4" />
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
            <DialogDescription>
              范围在创建时确定：项目会话只使用该项目论文，个人全库会话覆盖整个论文库。
            </DialogDescription>
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
                onValueChange={(value) => {
                  if (value === "library") {
                    setScope("library")
                    setProjectId("")
                  } else {
                    setScope("project")
                    setProjectId(value)
                  }
                }}
              >
                <SelectTrigger id="session-scope" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="library">个人全库</SelectItem>
                  {projects.data?.items.map((project) => (
                    <SelectItem key={project.id} value={project.id}>
                      项目：{project.name}
                    </SelectItem>
                  ))}
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

      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>删除会话「{deleting?.title ?? "未命名"}」</DialogTitle>
            <DialogDescription>
              会话历史与排队消息会被清理；论文库与项目不受影响。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => deleting && remove.mutate(deleting.id)}
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

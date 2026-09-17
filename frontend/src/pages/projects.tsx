import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FolderOpen, Pencil, Trash2 } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { PageHeader } from "@/app/app-shell"
import { queryKeys } from "@/app/query"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { CreateProjectDialog } from "@/components/projects/create-project-dialog"
import type { Project } from "@/lib/api"
import { useApi } from "@/lib/api/provider"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"

export function ProjectsPage() {
  const { api } = useApi()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [renaming, setRenaming] = useState<Project | null>(null)
  const [newName, setNewName] = useState("")
  const [deleting, setDeleting] = useState<Project | null>(null)

  const projects = useQuery({
    queryKey: queryKeys.projects({ limit: 100 }),
    queryFn: () => api.projects.list({ limit: 100 }),
  })

  const rename = useMutation({
    mutationFn: (input: { id: string; name: string }) =>
      api.projects.rename(input.id, { name: input.name }),
    onSuccess: (project) => {
      notifySuccess("已重命名", project.name)
      setRenaming(null)
      void queryClient.invalidateQueries({ queryKey: ["projects"] })
      void queryClient.invalidateQueries({ queryKey: queryKeys.project(project.id) })
    },
    onError: (error) => notifyError(error, "重命名失败"),
  })

  const remove = useMutation({
    mutationFn: (projectId: string) => api.projects.remove(projectId),
    onSuccess: () => {
      notifySuccess("项目已删除")
      setDeleting(null)
      void queryClient.invalidateQueries({ queryKey: ["projects"] })
    },
    onError: (error) => notifyError(error, "删除失败"),
  })

  const items = projects.data?.items ?? []

  return (
    <>
      <PageHeader
        title="项目"
        actions={
          <CreateProjectDialog
            onCreated={(projectId) => navigate(`/projects/${projectId}`)}
          />
        }
      />
      <div className="flex flex-1 flex-col gap-4 p-6">
        {projects.isError ? (
          <Alert variant="destructive">
            <AlertTitle>加载失败</AlertTitle>
            <AlertDescription>{describeError(projects.error)}</AlertDescription>
          </Alert>
        ) : null}

        {projects.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : items.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <FolderOpen />
              </EmptyMedia>
              <EmptyTitle>还没有项目</EmptyTitle>
            </EmptyHeader>
            <EmptyContent>
              <CreateProjectDialog
                onCreated={(projectId) => navigate(`/projects/${projectId}`)}
              />
            </EmptyContent>
          </Empty>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead>
                  <TableHead>描述</TableHead>
                  <TableHead>文献数</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((project) => (
                  <TableRow key={project.id}>
                    <TableCell>
                      <Link className="font-medium underline-offset-4 hover:underline" to={`/projects/${project.id}`}>
                        {project.name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-sm truncate">
                      {project.description ?? "—"}
                    </TableCell>
                    <TableCell>{project.paper_count}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setRenaming(project)
                            setNewName(project.name)
                          }}
                        >
                          <Pencil data-icon="inline-start" />
                          改名
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setDeleting(project)}
                        >
                          <Trash2 data-icon="inline-start" />
                          删除
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <Dialog open={Boolean(renaming)} onOpenChange={(open) => !open && setRenaming(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>重命名项目</DialogTitle>
          </DialogHeader>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              if (renaming) {
                rename.mutate({ id: renaming.id, name: newName.trim() })
              }
            }}
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="rename">名称</Label>
              <Input
                id="rename"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                required
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={rename.isPending || !newName.trim()}>
                保存
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除项目「{deleting?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              项目中的会话会一并删除，文献库不受影响。
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

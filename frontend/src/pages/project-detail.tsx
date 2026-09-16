import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, MessageSquarePlus } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"

import { PageHeader } from "@/app/app-shell"
import { queryKeys } from "@/app/query"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { AddPapersDialog } from "@/components/projects/add-papers-dialog"
import { ImportDialog } from "@/components/papers/import-dialog"
import { ProcessingBadge } from "@/components/papers/capability-badges"
import { PaperDetailSheet } from "@/components/papers/paper-detail-sheet"
import { useApi } from "@/lib/api/provider"
import { describeError, notifyError } from "@/lib/errors"

export function ProjectDetailPage() {
  const { projectId = "" } = useParams()
  const { api } = useApi()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [selectedPaper, setSelectedPaper] = useState<string | null>(null)

  const project = useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => api.projects.detail(projectId),
    enabled: Boolean(projectId),
  })

  const papers = useQuery({
    queryKey: queryKeys.projectPapers(projectId, { limit: 100 }),
    queryFn: () => api.projects.papers(projectId, { limit: 100 }),
    enabled: Boolean(projectId),
  })

  const sessions = useQuery({
    queryKey: queryKeys.sessions({ scope: "project", projectId }),
    queryFn: () => api.sessions.list({ scope: "project", project_id: projectId }),
    enabled: Boolean(projectId),
  })

  const createSession = useMutation({
    mutationFn: () =>
      api.sessions.create({
        project_id: projectId,
        title: project.data?.name ?? "项目会话",
      }),
    onSuccess: (session) => navigate(`/sessions/${session.id}`),
    onError: (error) => notifyError(error, "创建会话失败"),
  })

  if (project.isError) {
    return (
      <>
        <PageHeader title="项目详情" />
        <div className="p-6">
          <Alert variant="destructive">
            <AlertTitle>无法读取项目</AlertTitle>
            <AlertDescription>{describeError(project.error)}</AlertDescription>
          </Alert>
        </div>
      </>
    )
  }

  const items = papers.data?.items ?? []

  return (
    <>
      <PageHeader
        title={project.data?.name ?? "项目详情"}
        actions={
          <>
            <Button variant="ghost" asChild>
              <Link to="/projects">
                <ArrowLeft className="size-4" />
                返回
              </Link>
            </Button>
            <AddPapersDialog
              projectId={projectId}
              existingPaperIds={items.map((item) => item.id)}
            />
            <ImportDialog
              projectId={projectId}
              onImported={() => {
                void queryClient.invalidateQueries({ queryKey: ["project-papers"] })
              }}
            />
            <Button
              disabled={createSession.isPending}
              onClick={() => createSession.mutate()}
            >
              <MessageSquarePlus className="size-4" />
              新建项目会话
            </Button>
          </>
        }
      />

      <div className="flex flex-1 flex-col gap-6 p-6">
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium">项目论文（{papers.data?.total ?? 0}）</h2>
          {papers.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : items.length === 0 ? (
            <Card>
              <CardContent className="text-muted-foreground py-8 text-center text-sm">
                项目还没有论文。用“添加论文”从个人库选择，或直接按 DOI/arXiv 导入。
              </CardContent>
            </Card>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>标题</TableHead>
                    <TableHead>能力</TableHead>
                    <TableHead>处理</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((paper) => (
                    <TableRow
                      key={paper.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedPaper(paper.id)}
                    >
                      <TableCell className="max-w-lg">
                        <p className="truncate font-medium">
                          {paper.title ?? paper.original_filename ?? "未命名条目"}
                        </p>
                        <p className="text-muted-foreground truncate text-xs">
                          {paper.authors.slice(0, 3).join("、") || "作者未知"}
                          {paper.year ? ` · ${paper.year}` : ""}
                        </p>
                      </TableCell>
                      <TableCell>
                        {paper.capabilities.has_fulltext ? (
                          <Badge variant="secondary">可检索全文</Badge>
                        ) : (
                          <Badge variant="outline">待补全文</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <ProcessingBadge processing={paper.processing} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium">项目会话（{sessions.data?.total ?? 0}）</h2>
          {sessions.data?.items.length ? (
            <ul className="flex flex-col gap-1">
              {sessions.data.items.map((session) => (
                <li key={session.id}>
                  <Link
                    className="hover:bg-accent/60 flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                    to={`/sessions/${session.id}`}
                  >
                    <span>{session.title ?? "未命名会话"}</span>
                    <span className="text-muted-foreground text-xs">
                      等待投递 {session.pending.steering + session.pending.follow_up}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">
              还没有项目会话。项目会话只覆盖该项目论文，创建后范围不可修改。
            </p>
          )}
        </section>
      </div>

      <PaperDetailSheet
        paperId={selectedPaper}
        onOpenChange={(open) => !open && setSelectedPaper(null)}
      />
    </>
  )
}

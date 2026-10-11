import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { BookOpen, FileUp, RefreshCw, Search } from "lucide-react"
import { useRef, useState } from "react"
import { useNavigate } from "react-router-dom"

import { queryKeys } from "@/app/query"
import { Alert, AlertDescription, AlertTitle } from "@upstream/components/ui/alert"
import { Badge } from "@upstream/components/ui/badge"
import { Button } from "@upstream/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@upstream/components/ui/empty"
import { Spinner } from "@upstream/components/ui/spinner"
import { Input } from "@upstream/components/ui/input"
import { Skeleton } from "@upstream/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@upstream/components/ui/table"
import { ImportDialog } from "@/components/papers/import-dialog"
import { PaperStatusBadge } from "@/components/papers/paper-status"
import { PAPER_SOURCE_LABEL } from "@/lib/api/types"
import { useApi } from "@/lib/api/provider"
import { useAgentUi } from "@/lib/agent-ui"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"

const PAGE_SIZE = 20

export function LibraryPage() {
  const { api } = useApi()
  const agentUi = useAgentUi()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const fileInput = useRef<HTMLInputElement>(null)

  const [query, setQuery] = useState("")
  const [offset, setOffset] = useState(0)

  const papers = useQuery({
    queryKey: queryKeys.papers({ q: query, offset }),
    queryFn: () =>
      api.library.list({ q: query || undefined, limit: PAGE_SIZE, offset }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      const busy = items.some(
        (item) =>
          item.processing.status === "queued" || item.processing.status === "running",
      )
      return busy ? 2000 : false
    },
  })

  const upload = useMutation({
    mutationFn: (file: File) => api.library.upload(file),
    onSuccess: () => {
      notifySuccess("上传成功")
      void queryClient.invalidateQueries({ queryKey: ["papers"] })
    },
    onError: (error) => notifyError(error, "上传失败"),
  })

  const items = papers.data?.items ?? []

  return (
    <>
      <header className="flex h-12 shrink-0 items-center justify-between gap-3 overflow-x-auto border-b px-6">
        <h1 className="sr-only">文献库</h1>
        <div className="relative w-full max-w-sm">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            className="pl-9"
            aria-label="搜索文献"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setOffset(0)
            }}
          />
        </div>
        <div className="flex items-center gap-2">
            <Button
              onClick={() => fileInput.current?.click()}
              disabled={upload.isPending}
            >
              {upload.isPending ? (
                <Spinner data-icon="inline-start" />
              ) : (
                <FileUp data-icon="inline-start" />
              )}
              上传 PDF
            </Button>
            <ImportDialog
              onImported={() => {
                void queryClient.invalidateQueries({ queryKey: ["papers"] })
              }}
            />
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="刷新"
              onClick={() => void papers.refetch()}
            >
              <RefreshCw />
            </Button>
        </div>
      </header>
      <input
        ref={fileInput}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) {
            upload.mutate(file)
          }
          event.target.value = ""
        }}
      />

      <div className="flex flex-1 flex-col gap-4 p-6">
        {papers.isError ? (
          <Alert variant="destructive">
            <AlertTitle>加载失败</AlertTitle>
            <AlertDescription>{describeError(papers.error)}</AlertDescription>
          </Alert>
        ) : null}

        {papers.isPending ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : items.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <BookOpen />
              </EmptyMedia>
              <EmptyTitle>{query ? "没有匹配的文献" : "还没有文献"}</EmptyTitle>
            </EmptyHeader>
            {!query ? (
              <EmptyContent>
                <Button onClick={() => fileInput.current?.click()}>
                  <FileUp data-icon="inline-start" />
                  上传 PDF
                </Button>
              </EmptyContent>
            ) : null}
          </Empty>
        ) : (
          <div className="border-y">
            <Table>
              <TableHeader className="bg-muted/30">
                <TableRow>
                  <TableHead>标题</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((paper) => (
                  <TableRow
                    key={paper.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/library/${paper.id}`, { state: { from: "/library" } })}
                  >
                    <TableCell className="max-w-md">
                      <p className="truncate font-medium">
                        {paper.title ?? paper.original_filename ?? "未命名条目"}
                      </p>
                      <p className="text-muted-foreground truncate text-xs">
                        {paper.authors.slice(0, 3).join("、") || "作者未知"}
                        {paper.year ? ` · ${paper.year}` : ""}
                      </p>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{PAPER_SOURCE_LABEL[paper.source]}</Badge>
                    </TableCell>
                    <TableCell>
                      <PaperStatusBadge
                        capabilities={paper.capabilities}
                        processing={paper.processing}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      {!agentUi && <Button
                        size="sm"
                        variant="ghost"
                        onClick={(event) => {
                          event.stopPropagation()
                          void (async () => {
                            const session = await api.sessions.create({
                              title: paper.title ?? "文献提问",
                            })
                            navigate(`/sessions/${session.id}`)
                          })()
                        }}
                      >
                        提问
                      </Button>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {(papers.data?.total ?? 0) > PAGE_SIZE ? (
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground text-xs">
              共 {papers.data?.total} 条，当前 {offset + 1}–
              {Math.min(offset + PAGE_SIZE, papers.data?.total ?? 0)}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + PAGE_SIZE >= (papers.data?.total ?? 0)}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                下一页
              </Button>
            </div>
          </div>
        ) : null}
      </div>

    </>
  )
}

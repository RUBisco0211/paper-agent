import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  BookOpen,
  FileUp,
  FolderPlus,
  Info,
  RefreshCw,
  Search,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"

import { queryKeys } from "@/app/query"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/Alert"
import { Button } from "@/components/ui/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog"
import {
  Empty,
  EmptyContent,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/Empty"
import { Input } from "@/components/ui/Input"
import { Label } from "@/components/ui/Label"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select"
import { Skeleton } from "@/components/ui/Skeleton"
import { Spinner } from "@/components/ui/Spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/Table"
import { ImportDialog } from "@/components/papers/ImportDialog"
import { PaperDetailSheet } from "@/components/papers/PaperDetailSheet"
import { useApi } from "@/components/providers/ApiProvider"
import { useAgentUi } from "@/components/providers/AgentUiProvider"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue"
import type { UserPaperSummary } from "@/types/business"

const PAGE_SIZE = 20

/** Columns the reader can reorder by. */
type SortKey = "title" | "year"
type SortDirection = "asc" | "desc"

export function LibraryPage() {
  const { api } = useApi()
  const agentUi = useAgentUi()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const fileInput = useRef<HTMLInputElement>(null)

  const [query, setQuery] = useState("")
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection } | null>(
    null,
  )
  const search = useDebouncedValue(query.trim(), 300)
  const [addingTo, setAddingTo] = useState<UserPaperSummary | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [projectFilter, setProjectFilter] = useState<string>("none")

  const projects = useQuery({
    queryKey: queryKeys.projects({ limit: 100 }),
    queryFn: () => api.projects.list({ limit: 100 }),
  })



  const papers = useQuery({
    queryKey: queryKeys.papers({ q: search, offset }),
    queryFn: () =>
      api.library.list({ q: search || undefined, limit: PAGE_SIZE, offset }),
  })

  // Coming back to this page should show what the queue finished meanwhile.
  useEffect(() => {
    void papers.refetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const upload = useMutation({
    mutationFn: (file: File) => api.library.upload(file),
    onSuccess: () => {
      notifySuccess("上传成功")
      void queryClient.invalidateQueries({ queryKey: ["papers"] })
    },
    onError: (error) => notifyError(error, "上传失败"),
  })

  // Sorting applies to the page in hand: the query already brought every field
  // these columns show, and paging stays server-side.
  const items = useMemo(() => {
    const source = papers.data?.items ?? []
    const rows = [
      // Each row already carries its projects, so the filter needs no extra
      // request and combines with whatever the search returned.
      ...(projectFilter === "none"
        ? source
        : source.filter((item) => (item.project_ids ?? []).includes(projectFilter))),
    ]
    if (sort === null) return rows
    const sign = sort.direction === "asc" ? 1 : -1
    return rows.sort((left, right) => {
      if (sort.key === "title") {
        return sign * compareText(left.title ?? "", right.title ?? "")
      }
      return sign * compareNumber(left.year, right.year)
    })
  }, [papers.data, sort, projectFilter])

  function toggleSort(key: SortKey) {
    setSort((current) => {
      if (current?.key !== key) return { key, direction: "asc" }
      if (current.direction === "asc") return { key, direction: "desc" }
      return null
    })
  }

  return (
    <>
      <header
        data-slot="app-toolbar"
        className="flex h-(--app-toolbar-height) shrink-0 items-center border-b px-4"
      >
        <h1 className="font-medium">文献库</h1>
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
        <div className="flex items-center gap-2">
          <div className="relative w-full max-w-sm">
            <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
            <Input
              className="pl-9"
              aria-label="搜索文献"
              placeholder="搜索标题"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setOffset(0)
              }}
            />
          </div>
          <Select value={projectFilter} onValueChange={(value) => setProjectFilter(value)}>
            <SelectTrigger className="w-44" aria-label="按项目筛选">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="none">全部文献</SelectItem>
                {(projects.data?.items ?? []).map((project) => (
                  <SelectItem key={project.id} value={project.id}>
                    {project.name}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          <div className="ml-auto flex items-center gap-2">
            <Button
              disabled={upload.isPending}
              onClick={() => fileInput.current?.click()}
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
              tooltip="刷新"
              onClick={() => void papers.refetch()}
            >
              <RefreshCw />
            </Button>
          </div>
        </div>

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
              <EmptyTitle>{search ? "没有匹配的文献" : "还没有文献"}</EmptyTitle>
            </EmptyHeader>
            {!search ? (
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
                  <SortableHead
                    label="标题"
                    column="title"
                    sort={sort}
                    onSort={toggleSort}
                  />
                  <TableHead>DOI</TableHead>
                  <TableHead>期刊 / 会议</TableHead>
                  <SortableHead
                    label="年份"
                    column="year"
                    sort={sort}
                    onSort={toggleSort}
                  />
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((paper) => (
                  <TableRow
                    key={paper.id}
                    className="cursor-pointer"
                    onClick={() =>
                      navigate(`/library/${paper.id}`, { state: { from: "/library" } })
                    }
                  >
                    <TableCell className="max-w-md">
                      <p className="truncate font-medium">
                        {paper.title ?? "未命名条目"}
                      </p>
                      <p className="text-muted-foreground truncate text-xs">
                        {paper.authors.slice(0, 3).join("、") || "作者未知"}
                      </p>
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-56 truncate">
                      {paper.doi ?? "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-48 truncate">
                      {paper.venue ?? "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {paper.year ?? "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div
                        className="flex items-center justify-end gap-1"
                        onClick={(event) => event.stopPropagation()}
                      >
                        <Button
                          tooltip="查看详情"
                          variant="ghost"
                          size="icon-sm"
                          aria-label="查看详情"
                          onClick={() => setDetailId(paper.id)}
                        >
                          <Info />
                        </Button>
                        <Button
                          tooltip="加入项目"
                          variant="ghost"
                          size="icon-sm"
                          aria-label="加入项目"
                          onClick={() => setAddingTo(paper)}
                        >
                          <FolderPlus />
                        </Button>
                        {!agentUi && (
                          <Button
                            tooltip="就此文献提问"
                            variant="ghost"
                            size="icon-sm"
                            aria-label="就此文献提问"
                            onClick={() => {
                              void (async () => {
                                const session = await api.sessions.create({
                                  title: paper.title ?? "文献提问",
                                })
                                navigate(`/sessions/${session.id}`)
                              })()
                            }}
                          >
                            <BookOpen />
                          </Button>
                        )}
                      </div>
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

      <PaperDetailSheet
        paperId={detailId}
        onOpenChange={(next) => {
          if (!next) setDetailId(null)
        }}
      />
      {addingTo && (
        <AddToProjectDialog
          entry={addingTo}
          onClose={() => setAddingTo(null)}
        />
      )}
    </>
  )
}

/** A header cell that reorders the rows, and shows which order is active. */
function SortableHead({
  label,
  column,
  sort,
  onSort,
}: {
  label: string
  column: SortKey
  sort: { key: SortKey; direction: SortDirection } | null
  onSort: (column: SortKey) => void
}) {
  const active = sort?.key === column
  const Icon = !active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown
  return (
    <TableHead>
      <button
        type="button"
        onClick={() => onSort(column)}
        aria-label={`按${label}排序`}
        aria-sort={
          active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"
        }
        className="hover:text-foreground flex items-center gap-1"
      >
        {label}
        <Icon aria-hidden="true" className="size-3.5" />
      </button>
    </TableHead>
  )
}

/** Pick one of the reader's projects and put this entry into it. */
function AddToProjectDialog({
  entry,
  onClose,
}: {
  entry: UserPaperSummary
  onClose: () => void
}) {
  const { api } = useApi()
  const queryClient = useQueryClient()
  const [projectId, setProjectId] = useState("")

  const projects = useQuery({
    queryKey: queryKeys.projects({ limit: 100 }),
    queryFn: () => api.projects.list({ limit: 100 }),
  })

  const add = useMutation({
    mutationFn: () => api.projects.addPapers(projectId, [entry.id]),
    onSuccess: () => {
      notifySuccess("已加入项目")
      void queryClient.invalidateQueries({ queryKey: ["project-papers"] })
      onClose()
    },
    onError: (error) => notifyError(error, "加入失败"),
  })

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      {/* A dialog is a grid: every child defaults to min-width:auto, so a long
          title can widen the whole box past its own max-width. Constrain the
          box and let each row shrink instead. */}
      <DialogContent className="w-[min(32rem,calc(100vw-2rem))] max-w-[calc(100vw-2rem)]">
        <DialogHeader className="min-w-0">
          <DialogTitle>加入项目</DialogTitle>
          <DialogDescription>选择要把这条文献放进哪个项目。</DialogDescription>
          <p
            className="w-full min-w-0 font-medium break-words"
            title={entry.title ?? undefined}
          >
            {entry.title ?? "未命名条目"}
          </p>
        </DialogHeader>
        <div className="flex w-full min-w-0 flex-col gap-2">
          <Label htmlFor="add-to-project">项目</Label>
          <Select value={projectId} onValueChange={setProjectId}>
            <SelectTrigger id="add-to-project" className="w-full">
              <SelectValue placeholder="选择一个项目" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {(projects.data?.items ?? []).map((project) => (
                  <SelectItem key={project.id} value={project.id}>
                    {project.name}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          {projects.isError ? (
            <p role="alert" className="text-destructive text-sm">
              项目列表加载失败
            </p>
          ) : null}
        </div>
        <DialogFooter className="min-w-0">
          <Button variant="outline" onClick={onClose} disabled={add.isPending}>
            取消
          </Button>
          <Button
            onClick={() => add.mutate()}
            disabled={!projectId || add.isPending}
          >
            {add.isPending ? <Spinner data-icon="inline-start" /> : null}
            加入
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function compareText(left: string, right: string): number {
  return left.localeCompare(right, "zh-CN")
}

function compareNumber(left: number | null | undefined, right: number | null | undefined): number {
  // Rows without a year sort last in both directions.
  if (left == null && right == null) return 0
  if (left == null) return 1
  if (right == null) return -1
  return left - right
}

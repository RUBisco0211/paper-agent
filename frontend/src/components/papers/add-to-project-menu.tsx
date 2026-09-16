import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FolderPlus } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useApi } from "@/lib/api/provider"
import { notifyError, notifySuccess } from "@/lib/errors"
import { queryKeys } from "@/app/query"

/** Projects are a subset of the personal library; adding never moves a paper. */
export function AddToProjectMenu({
  paperId,
  disabled,
}: {
  paperId: string
  disabled?: boolean
}) {
  const { api } = useApi()
  const queryClient = useQueryClient()
  const projects = useQuery({
    queryKey: queryKeys.projects({ limit: 100 }),
    queryFn: () => api.projects.list({ limit: 100 }),
  })

  const add = useMutation({
    mutationFn: (projectId: string) => api.projects.addPapers(projectId, [paperId]),
    onSuccess: (result, projectId) => {
      if (result.already_present.length > 0) {
        notifySuccess("该论文已在项目中")
      } else {
        notifySuccess("已加入项目")
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.projectPapers(projectId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
      void queryClient.invalidateQueries({ queryKey: ["projects"] })
    },
    onError: (error) => notifyError(error, "加入项目失败"),
  })

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" disabled={disabled}>
          <FolderPlus className="size-4" />
          加入项目
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>选择项目</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {projects.data?.items.length ? (
          projects.data.items.map((project) => (
            <DropdownMenuItem
              key={project.id}
              onSelect={() => add.mutate(project.id)}
            >
              <span className="truncate">{project.name}</span>
            </DropdownMenuItem>
          ))
        ) : (
          <DropdownMenuItem disabled>还没有项目</DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

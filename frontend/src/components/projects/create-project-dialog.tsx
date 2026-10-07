import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { Button } from "@upstream/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@upstream/components/ui/dialog"
import { Input } from "@upstream/components/ui/input"
import { Field, FieldGroup, FieldLabel } from "@upstream/components/ui/field"
import { Spinner } from "@upstream/components/ui/spinner"
import { Textarea } from "@upstream/components/ui/textarea"
import { useApi } from "@/lib/api/provider"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"

export function CreateProjectDialog({
  trigger,
  onCreated,
}: {
  trigger?: React.ReactNode
  onCreated?: (projectId: string) => void
}) {
  const { api } = useApi()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => api.projects.create({ name: name.trim(), description }),
    onSuccess: (project) => {
      notifySuccess("项目已创建", `${project.name} 目前还没有文献`)
      void queryClient.invalidateQueries({ queryKey: ["projects"] })
      setOpen(false)
      setName("")
      setDescription("")
      onCreated?.(project.id)
    },
    onError: (cause) => {
      setError(describeError(cause))
      notifyError(cause, "创建项目失败")
    },
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? <Button>新建项目</Button>}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建项目</DialogTitle>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            create.mutate()
          }}
        >
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="project-name">名称</FieldLabel>
              <Input
                id="project-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="project-description">描述</FieldLabel>
              <Textarea
                id="project-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
          </FieldGroup>
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
          <DialogFooter>
            <Button type="submit" disabled={create.isPending || !name.trim()}>
              {create.isPending ? <Spinner data-icon="inline-start" /> : null}
              创建
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

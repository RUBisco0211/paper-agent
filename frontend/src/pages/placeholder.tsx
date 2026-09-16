import { Construction } from "lucide-react"

import { PageHeader } from "@/app/app-shell"

/** Temporary state for routes whose page is not built yet. */
export function PlaceholderPage({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <div className="flex flex-1 items-center justify-center p-10">
        <div className="text-muted-foreground flex flex-col items-center gap-2 text-sm">
          <Construction className="size-6" />
          <p>该页面尚未实现</p>
        </div>
      </div>
    </>
  )
}

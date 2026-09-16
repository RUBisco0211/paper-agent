import { useEffect, useState } from "react"

import { useApi } from "@/lib/api/provider"
import { describeError } from "@/lib/errors"
import { Skeleton } from "@/components/ui/skeleton"

/**
 * Renders the authorized PDF.
 *
 * The file is fetched with the access token and turned into a blob URL, because
 * the PDF endpoint requires an Authorization header that an <iframe src> cannot
 * send. `#page=` works with the browser's built-in viewer.
 */
export function PdfViewer({
  paperId,
  page,
  className,
}: {
  paperId: string
  page?: number | null
  className?: string
}) {
  const { api } = useApi()
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let revoked: string | null = null
    let cancelled = false
    void (async () => {
      try {
        const blob = await api.library.pdfBlob(paperId)
        if (cancelled) {
          return
        }
        const objectUrl = URL.createObjectURL(blob)
        revoked = objectUrl
        setUrl(objectUrl)
        setError(null)
      } catch (cause) {
        if (!cancelled) {
          setError(describeError(cause))
        }
      }
    })()
    return () => {
      cancelled = true
      if (revoked) {
        URL.revokeObjectURL(revoked)
      }
      setUrl(null)
    }
  }, [api, paperId])

  if (error) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center p-6 text-sm">
        {error}
      </div>
    )
  }
  if (!url) {
    return (
      <div className="flex h-full flex-col gap-2 p-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-full w-full" />
      </div>
    )
  }
  const src = page ? `${url}#page=${page}&zoom=page-width` : `${url}#zoom=page-width`
  return (
    <iframe
      key={src}
      title="论文原文"
      src={src}
      className={className ?? "h-full w-full border-0"}
    />
  )
}

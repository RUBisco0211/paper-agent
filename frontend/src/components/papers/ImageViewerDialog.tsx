import { Download, Minus, Plus, RotateCcw, RotateCw } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog"

export interface ImageViewerTarget {
  source: string
  title: string
  /** Download name; the caller knows the media type, the dialog only has bytes. */
  filename?: string
}

function extensionFor(source: string): string {
  const match = /^data:(image\/[a-z+.-]+);/i.exec(source)
  if (!match) return "png"
  return match[1].split("/")[1].replace("jpeg", "jpg")
}

function downloadName(target: ImageViewerTarget): string {
  if (target.filename) return target.filename
  return `${target.title || "figure"}.${extensionFor(target.source)}`
}

/**
 * The one large-image viewer: zoom, 90° rotation and download, shared by the
 * reading page and the chat tool cards so a figure opens the same way anywhere.
 */
export function ImageViewerDialog({
  target,
  onOpenChange,
}: {
  target: ImageViewerTarget | null
  onOpenChange: (target: ImageViewerTarget | null) => void
}) {
  const [zoom, setZoom] = useState(1)
  const [rotation, setRotation] = useState(0)
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null)
  const [box, setBox] = useState({ width: 0, height: 0 })
  const boxRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setZoom(1)
    setRotation(0)
    setNatural(null)
  }, [target])

  useEffect(() => {
    const element = boxRef.current
    if (!element) return
    const measure = () => setBox({ width: element.clientWidth, height: element.clientHeight })
    measure()
    if (typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [target])

  const sideways = rotation === 90 || rotation === 270
  // 100% fits the picture in the pane; rotation swaps the axis it fits against.
  const fit =
    natural && box.width > 0 && box.height > 0
      ? Math.min(
          box.width / (sideways ? natural.height : natural.width),
          box.height / (sideways ? natural.width : natural.height),
        )
      : 0
  const width = natural ? natural.width * fit * zoom : 0
  const height = natural ? natural.height * fit * zoom : 0
  const measured = width > 0 && height > 0

  return (
    <Dialog open={Boolean(target)} onOpenChange={(open) => { if (!open) onOpenChange(null) }}>
      <DialogContent className="flex h-[92vh] w-[96vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none">
        <div data-slot="app-toolbar" className="flex h-(--app-toolbar-height) shrink-0 items-center gap-2 border-b px-4 pr-12">
          <DialogTitle className="min-w-0 flex-1 truncate">{target?.title}</DialogTitle>
          <DialogDescription className="sr-only">放大、旋转或下载图片以查看细节</DialogDescription>
          <Button variant="ghost" size="icon-sm" aria-label="缩小图片" disabled={zoom <= 0.5} onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))}><Minus /></Button>
          <span className="min-w-10 text-center text-xs tabular-nums">{Math.round(zoom * 100)}%</span>
          <Button variant="ghost" size="icon-sm" aria-label="放大图片" disabled={zoom >= 4} onClick={() => setZoom((value) => Math.min(4, value + 0.25))}><Plus /></Button>
          <Button variant="ghost" size="icon-sm" aria-label="向左旋转" title="向左旋转 90°" onClick={() => setRotation((value) => (value + 270) % 360)}><RotateCcw /></Button>
          <Button variant="ghost" size="icon-sm" aria-label="向右旋转" title="向右旋转 90°" onClick={() => setRotation((value) => (value + 90) % 360)}><RotateCw /></Button>
          {target && (
            <Button variant="ghost" size="icon-sm" asChild>
              <a href={target.source} download={downloadName(target)} aria-label="下载图片" title="下载图片"><Download /></a>
            </Button>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-muted/30 p-4">
          <div ref={boxRef} className="flex min-h-full min-w-full items-center justify-center">
            {target && (
              <div
                className="relative shrink-0"
                style={measured && natural
                  ? {
                      width: sideways ? height : width,
                      height: sideways ? width : height,
                    }
                  : { width: "100%" }}
              >
                <img
                  src={target.source}
                  alt={target.title}
                  onLoad={(event) => setNatural({
                    width: event.currentTarget.naturalWidth,
                    height: event.currentTarget.naturalHeight,
                  })}
                  className="object-contain"
                  style={measured && natural
                    ? {
                        position: "absolute",
                        width,
                        height,
                        left: sideways ? (height - width) / 2 : 0,
                        top: sideways ? (width - height) / 2 : 0,
                        transform: `rotate(${rotation}deg)`,
                      }
                    : {
                        width: "100%",
                        height: "auto",
                        maxWidth: "none",
                        transform: `rotate(${rotation}deg)`,
                      }}
                />
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

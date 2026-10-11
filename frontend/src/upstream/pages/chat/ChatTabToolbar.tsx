import { useQuery } from "@tanstack/react-query"
import { Command as CommandPrimitive } from "cmdk"
import { ChevronLeft, ChevronRight, PanelLeftClose, PanelLeftOpen, Plus, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { useApi } from "@/lib/api/provider"
import type { BoundSession } from "@/lib/agent-sessions"
import { Button } from "@upstream/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@upstream/components/ui/dialog"
import { chatPath } from "./chat-view"
import { isDraftTabPath } from "./chat-tabs"

export function ChatTabToolbar({ paths, activePath, sessions, leftOpen, onToggleLeft, onSelect, onClose }: {
  paths: string[]
  activePath: string
  sessions: BoundSession[]
  leftOpen: boolean
  onToggleLeft: () => void
  onSelect: (path: string) => void
  onClose: (path: string) => void
}) {
  const { api } = useApi()
  const [pickerOpen, setPickerOpen] = useState(false)
  const stripRef = useRef<HTMLDivElement>(null)
  const [scrollState, setScrollState] = useState({ back: false, forward: false })
  const projects = useQuery({ queryKey: ["sidebar-projects"], queryFn: () => api.projects.list({ limit: 100 }) })

  useEffect(() => {
    const strip = stripRef.current
    if (!strip) return
    const update = () => setScrollState({
      back: strip.scrollLeft > 1,
      forward: strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1,
    })
    update()
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update)
    observer?.observe(strip)
    window.addEventListener("resize", update)
    return () => { observer?.disconnect(); window.removeEventListener("resize", update) }
  }, [paths.length])

  useEffect(() => {
    const strip = stripRef.current
    const active = Array.from(strip?.children ?? []).find((item) => item.getAttribute("data-tab-path") === activePath)
    if (!strip || !active || !strip.scrollBy) return
    const bounds = strip.getBoundingClientRect()
    const tab = active.getBoundingClientRect()
    if (tab.left < bounds.left) strip.scrollBy({ left: tab.left - bounds.left, behavior: "smooth" })
    else if (tab.right > bounds.right) strip.scrollBy({ left: tab.right - bounds.right, behavior: "smooth" })
  }, [activePath, paths])

  function choose(path: string) {
    onSelect(path)
    setPickerOpen(false)
  }

  return <>
    <header className="flex h-12 shrink-0 items-center gap-1 border-b bg-[#f7f8f9] px-2" aria-label="会话标签栏">
      <div className="flex shrink-0 items-center gap-0.5">
        <Button variant="ghost" size="icon-sm" aria-label={leftOpen ? "收起会话侧栏" : "展开会话侧栏"} title={leftOpen ? "收起会话侧栏" : "展开会话侧栏"} onClick={onToggleLeft}>{leftOpen ? <PanelLeftClose /> : <PanelLeftOpen />}</Button>
      </div>
      <div aria-hidden="true" className="mx-2 h-5 w-px shrink-0 bg-border" />
      {scrollState.back && <Button variant="ghost" size="icon-xs" aria-label="向左滚动会话标签" onClick={() => stripRef.current?.scrollBy({ left: -240, behavior: "smooth" })}><ChevronLeft /></Button>}
      <div ref={stripRef} className="flex h-full min-w-0 flex-1 items-center gap-1 overflow-x-auto pl-1 [scrollbar-width:none]" role="tablist" aria-label="打开的会话" onScroll={(event) => {
        const strip = event.currentTarget
        setScrollState({ back: strip.scrollLeft > 1, forward: strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1 })
      }}>
        {paths.map((path) => {
          const session = sessions.find((item) => chatPath(item) === path)
          const projectName = session?.binding.project_id
            ? projects.data?.items.find((project) => project.id === session.binding.project_id)?.name ?? "项目"
            : "全局"
          const title = isDraftTabPath(path) ? "新会话" : `${session?.session.session.config.name || "会话"} - ${projectName}`
          return <div key={path} data-tab-path={path} className="flex h-9 min-w-24 max-w-72 flex-[1_1_18rem] items-center rounded-lg text-muted-foreground transition-colors data-[active=false]:hover:bg-background/60 data-[active=true]:bg-background data-[active=true]:text-foreground data-[active=true]:shadow-sm data-[active=true]:ring-1 data-[active=true]:ring-border/60" data-active={path === activePath}>
            <button type="button" role="tab" aria-selected={path === activePath} title={title} className="min-w-0 flex-1 truncate px-3 text-left text-sm" onClick={() => onSelect(path)}>{title}</button>
            <Button variant="ghost" size="icon-xs" aria-label={`关闭${title}`} title="关闭标签" onClick={() => onClose(path)}><X /></Button>
          </div>
        })}
      </div>
      {scrollState.forward && <Button variant="ghost" size="icon-xs" aria-label="向右滚动会话标签" onClick={() => stripRef.current?.scrollBy({ left: 240, behavior: "smooth" })}><ChevronRight /></Button>}
      <Button variant="ghost" size="icon-sm" className="shrink-0" aria-label="添加会话标签" title="添加会话标签" onClick={() => setPickerOpen(true)}><Plus /></Button>
    </header>
    <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
      <DialogContent className="gap-0 p-0 sm:max-w-lg">
        <DialogHeader className="sr-only"><DialogTitle>打开会话</DialogTitle><DialogDescription>搜索并打开已有会话</DialogDescription></DialogHeader>
        <CommandPrimitive className="flex min-h-0 flex-col" label="选择会话">
          <CommandPrimitive.Input autoFocus aria-label="搜索会话" placeholder="搜索会话…" className="h-11 border-b bg-transparent px-4 text-sm outline-none" />
          <CommandPrimitive.List className="max-h-80 overflow-y-auto p-2">
            <CommandPrimitive.Empty className="p-4 text-center text-sm text-muted-foreground">没有匹配的会话</CommandPrimitive.Empty>
            <CommandPrimitive.Group heading="新建" className="text-sm [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-muted-foreground">
              <CommandPrimitive.Item value="新建会话" onSelect={() => choose("/chat/new")} className="cursor-pointer rounded-md px-2 py-2 data-[selected=true]:bg-muted">新建会话</CommandPrimitive.Item>
            </CommandPrimitive.Group>
            {[{ id: null, name: "全局" }, ...(projects.data?.items ?? []).map((project) => ({ id: project.id, name: project.name }))].map((group) => {
              const groupSessions = sessions.filter((item) => item.binding.project_id === group.id)
              if (!groupSessions.length) return null
              return <CommandPrimitive.Group key={group.id ?? "global"} heading={group.name} className="text-sm [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-muted-foreground">
                {groupSessions.map((item) => <CommandPrimitive.Item key={item.session.session.id} value={`${item.session.session.config.name || "新会话"} ${group.name} ${item.session.session.created_at}`} onSelect={() => choose(chatPath(item))} className="flex cursor-pointer items-center rounded-md px-2 py-2 data-[selected=true]:bg-muted">
                  <span className="truncate">{item.session.session.config.name || "新会话"}</span>
                </CommandPrimitive.Item>)}
              </CommandPrimitive.Group>
            })}
          </CommandPrimitive.List>
        </CommandPrimitive>
      </DialogContent>
    </Dialog>
  </>
}

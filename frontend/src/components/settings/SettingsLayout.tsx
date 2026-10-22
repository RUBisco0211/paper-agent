import { Cpu, Globe } from "lucide-react"
import { NavLink, Outlet, useLocation } from "react-router-dom"

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
} from "@/components/ui/Sidebar"

const SECTIONS = [
  { to: "/settings/models", label: "模型", icon: Cpu },
  { to: "/settings/web-search", label: "网络搜索", icon: Globe },
]

const TITLES: Record<string, string> = {
  "/settings/models": "模型",
  "/settings/web-search": "网络搜索",
}

export function SettingsLayout() {
  const location = useLocation()
  const title = TITLES[location.pathname] ?? "设置"
  return (
    <SidebarProvider className="min-h-0 flex-1">
      <div className="flex h-full w-full">
        <Sidebar collapsible="none" className="border-r">
          <SidebarHeader className="h-(--app-toolbar-height) justify-center px-4 font-semibold">
            设置
          </SidebarHeader>
          <SidebarContent>
            <SidebarGroup>
              <SidebarGroupLabel>服务</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {SECTIONS.map((section) => (
                    <SidebarMenuItem key={section.to}>
                      <SidebarMenuButton asChild isActive={location.pathname === section.to}>
                        <NavLink to={section.to}>
                          <section.icon />
                          {section.label}
                        </NavLink>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </SidebarContent>
        </Sidebar>
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-background">
          <header
            data-slot="app-toolbar"
            className="flex h-(--app-toolbar-height) shrink-0 items-center border-b px-6"
          >
            <h1 className="font-medium">{title}</h1>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </SidebarProvider>
  )
}

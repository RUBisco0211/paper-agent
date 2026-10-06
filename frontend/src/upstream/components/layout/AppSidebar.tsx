import { BookOpen, CalendarDays, KeyRound, LogOut, MessageSquareText } from "lucide-react"
import { NavLink, useLocation, useNavigate } from "react-router-dom"

import { useAuth } from "@/lib/auth/provider"
import { Avatar, AvatarFallback } from "@upstream/components/ui/avatar"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@upstream/components/ui/dropdown-menu"
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@upstream/components/ui/sidebar"

const routes = [
  { to: "/chat", label: "对话", icon: MessageSquareText },
  { to: "/library", label: "文献库", icon: BookOpen },
  { to: "/calendar", label: "日历", icon: CalendarDays },
  { to: "/settings", label: "模型设置", icon: KeyRound },
]

export function AppSidebar() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  return <Sidebar collapsible="none" className="w-16 border-r [&_[data-slot=sidebar-container]]:w-16 [&_[data-slot=sidebar-inner]]:w-16">
    <SidebarHeader className="items-center px-2 pt-4">
      <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground text-sm font-semibold" aria-label="Paper Agent">P</span>
    </SidebarHeader>
    <SidebarContent className="pt-5">
      <SidebarGroup className="px-2"><SidebarGroupContent><SidebarMenu>
        {routes.map(({ to, label, icon: Icon }) => <SidebarMenuItem key={to}>
          <SidebarMenuButton asChild tooltip={{ children: label, hidden: false }} isActive={location.pathname === to || location.pathname.startsWith(`${to}/`)} className="mx-auto size-8! justify-center p-0!">
            <NavLink to={to} aria-label={label}><Icon /><span className="sr-only">{label}</span></NavLink>
          </SidebarMenuButton>
        </SidebarMenuItem>)}
      </SidebarMenu></SidebarGroupContent></SidebarGroup>
    </SidebarContent>
    <SidebarFooter className="items-center px-2 pb-4"><SidebarMenu><SidebarMenuItem>
      <DropdownMenu><DropdownMenuTrigger asChild><SidebarMenuButton size="lg" aria-label="账户" className="mx-auto size-8! justify-center p-0!">
        <Avatar className="size-7"><AvatarFallback>{(user?.display_name || user?.email || "?").slice(0, 1).toUpperCase()}</AvatarFallback></Avatar>
      </SidebarMenuButton></DropdownMenuTrigger>
        <DropdownMenuContent side="right" align="end" className="w-52">
          <DropdownMenuLabel className="truncate">{user?.email}</DropdownMenuLabel><DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => navigate("/settings")}><KeyRound />模型设置</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => void logout().then(() => navigate("/login", { replace: true }))}><LogOut />退出登录</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem></SidebarMenu></SidebarFooter>
  </Sidebar>
}

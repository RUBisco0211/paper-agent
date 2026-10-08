import { Outlet } from 'react-router-dom';
import { ImportQueueProvider } from '@/lib/import-queue-context';

import { AppSidebar } from '@upstream/components/layout/AppSidebar';
import { SidebarInset, SidebarProvider } from '@upstream/components/ui/sidebar';
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarHeader } from '@upstream/components/ui/sidebar';

export function AppLayout() {
	return (
		<ImportQueueProvider><div className="h-screen flex">
			<SidebarProvider style={{ '--sidebar-width': '4rem' } as React.CSSProperties}>
				<AppSidebar />
				<SidebarInset className="flex-1 overflow-hidden bg-background">
					<Outlet />
				</SidebarInset>
			</SidebarProvider>
		</div></ImportQueueProvider>
	);
}

export function SectionLayout({ title, section, children }: { title: string; section: string; children: React.ReactNode }) {
	return <SidebarProvider className="min-h-0 flex-1">
		<div className="flex h-full w-full">
			<Sidebar collapsible="none" className="border-r">
				<SidebarHeader className="px-4 py-5 font-semibold">{title}</SidebarHeader>
				<SidebarContent><SidebarGroup><SidebarGroupContent>
					<p className="rounded-md bg-sidebar-accent px-3 py-2 text-sm font-medium">{section}</p>
				</SidebarGroupContent></SidebarGroup></SidebarContent>
			</Sidebar>
			<main className="flex min-w-0 flex-1 flex-col overflow-y-auto bg-background">{children}</main>
		</div>
	</SidebarProvider>
}

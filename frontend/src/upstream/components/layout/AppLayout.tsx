import { Outlet } from 'react-router-dom';
import { ImportQueueProvider } from '@/lib/import-queue-context';

import { AppSidebar } from '@upstream/components/layout/AppSidebar';
import { SidebarInset, SidebarProvider } from '@upstream/components/ui/sidebar';

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

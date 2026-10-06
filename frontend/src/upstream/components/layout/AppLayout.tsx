import { Outlet } from 'react-router-dom';

import { AppSidebar } from '@upstream/components/layout/AppSidebar';
import { SidebarInset, SidebarProvider } from '@upstream/components/ui/sidebar';

export function AppLayout() {
	return (
		<div className="h-screen flex">
			<SidebarProvider>
				<AppSidebar />
				<SidebarInset className="flex-1 overflow-hidden bg-canvas">
					<Outlet />
				</SidebarInset>
			</SidebarProvider>
		</div>
	);
}

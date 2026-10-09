import { UNSAFE_LocationContext, useLocation, useOutlet } from 'react-router-dom';
import { useContext, useRef, type ReactNode } from 'react';
import { ImportQueueProvider } from '@/lib/import-queue-context';

import { AppSidebar } from '@upstream/components/layout/AppSidebar';
import { SidebarInset, SidebarProvider } from '@upstream/components/ui/sidebar';

export function AppLayout() {
	return (
		<ImportQueueProvider><div className="h-screen flex">
			<SidebarProvider style={{ '--sidebar-width': '4rem' } as React.CSSProperties}>
				<AppSidebar />
				<SidebarInset className="flex-1 overflow-hidden bg-background">
					<KeepAliveOutlet />
				</SidebarInset>
			</SidebarProvider>
		</div></ImportQueueProvider>
	);
}

const SAVED_SECTIONS = new Set(['chat', 'library', 'discover', 'scheduled', 'settings']);

export function KeepAliveOutlet() {
	const location = useLocation();
	const outlet = useOutlet();
	const liveContext = useContext(UNSAFE_LocationContext);
	const section = location.pathname.split('/')[1];
	const saved = useRef(new Map<string, { element: ReactNode; locationContext: typeof liveContext }>());
	if (!SAVED_SECTIONS.has(section)) return outlet;
	saved.current.set(section, { element: outlet, locationContext: liveContext });
	return <>{Array.from(saved.current, ([key, entry]) => (
		<div key={key} aria-hidden={key !== section} style={{ display: key === section ? 'flex' : 'none' }} className="h-full min-h-0 min-w-0 flex-1 flex-col">
			<UNSAFE_LocationContext.Provider value={entry.locationContext}>
				{entry.element}
			</UNSAFE_LocationContext.Provider>
		</div>
	))}</>;
}

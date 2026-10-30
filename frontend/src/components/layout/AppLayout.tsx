import { UNSAFE_LocationContext, useLocation, useOutlet } from 'react-router-dom';
import { useContext, useLayoutEffect, useRef, type ReactNode } from 'react';
import { ImportQueueProvider } from '@/components/providers/ImportQueueProvider';

import { AppSidebar } from '@/components/layout/AppSidebar';
import { ChatSidebarProvider } from '@/components/providers/ChatSidebarProvider';
import { SidebarInset, SidebarProvider } from '@/components/ui/Sidebar';

export function AppLayout() {
	return (
		<ImportQueueProvider><div className="h-screen flex">
			<SidebarProvider>
				<ChatSidebarProvider>
					<AppSidebar />
					<SidebarInset className="flex-1 overflow-hidden bg-background">
						<KeepAliveOutlet />
					</SidebarInset>
				</ChatSidebarProvider>
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
	const sectionNodes = useRef(new Map<string, HTMLDivElement>());
	const previousSection = useRef<string | null>(null);
	useLayoutEffect(() => {
		const changedSection = previousSection.current !== section;
		previousSection.current = section;
		if (section === 'chat' && !changedSection) return;
		const node = sectionNodes.current.get(section);
		if (!node) return;
		node.classList.remove('route-page-enter');
		void node.offsetWidth;
		node.classList.add('route-page-enter');
		return () => node.classList.remove('route-page-enter');
	}, [section, location.pathname]);
	if (!SAVED_SECTIONS.has(section)) return outlet;
	saved.current.set(section, { element: outlet, locationContext: liveContext });
	return <>{Array.from(saved.current, ([key, entry]) => (
		<div key={key} ref={(node) => { if (node) sectionNodes.current.set(key, node); else sectionNodes.current.delete(key); }} aria-hidden={key !== section} style={{ display: key === section ? 'flex' : 'none' }} className="h-full min-h-0 min-w-0 flex-1 flex-col">
			<UNSAFE_LocationContext.Provider value={entry.locationContext}>
				{entry.element}
			</UNSAFE_LocationContext.Provider>
		</div>
	))}</>;
}

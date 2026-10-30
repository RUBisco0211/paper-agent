import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

interface ChatSidebarVisibility {
	open: boolean;
	toggle: () => void;
}

const ChatSidebarContext = createContext<ChatSidebarVisibility | null>(null);

/** Standalone renders (tests, embedded pages) keep the panel on screen. */
const ALWAYS_OPEN: ChatSidebarVisibility = { open: true, toggle: () => {} };

/**
 * Whether the conversation's session list is on screen.
 *
 * The conversation layout owns the panel, but the control that folds it away is
 * the rail's 对话 button, so the state has to sit above both.
 */
export function ChatSidebarProvider({ children }: { children: ReactNode }) {
	const [open, setOpen] = useState(true);
	const toggle = useCallback(() => setOpen((value) => !value), []);
	const value = useMemo(() => ({ open, toggle }), [open, toggle]);
	return <ChatSidebarContext.Provider value={value}>{children}</ChatSidebarContext.Provider>;
}

export function useChatSidebarVisibility(): ChatSidebarVisibility {
	return useContext(ChatSidebarContext) ?? ALWAYS_OPEN;
}

import { useQuery } from "@tanstack/react-query";
import { usePanelRef } from "react-resizable-panels";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useOutlet } from "react-router-dom";

import { useApi } from "@/components/providers/ApiProvider";
import { useChatSidebarVisibility } from "@/components/providers/ChatSidebarProvider";
import { listBoundSessions } from "@/lib/agentSessions";
import { SidebarProvider } from "@/components/ui/Sidebar";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/Resizable";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import {
  ChatQuoteContext,
  type ChatQuoteReceiver,
  type PaperQuoteOpener,
} from "@/components/chat/chatQuoteContext";
import type { PaperOpen, QuoteReference } from "@/types/chat";
import { ConversationPapersPanel } from "@/components/chat/ConversationPapersPanel";
import { chatPath } from "@/components/chat/chatView";

export interface ChatWorkspaceContext {
  draftQuoteKey: string;
  draftProjectId: string;
  setDraftProjectId: (projectId: string) => void;
}

export function ChatPage() {
  const { api } = useApi();
  const navigate = useNavigate();
  const location = useLocation();
  const initialDraftProjectId =
    (location.state as { initialProjectId?: string | null } | null)
      ?.initialProjectId ?? "";
  const [draftScope, setDraftScope] = useState({
    key: location.key,
    projectId: initialDraftProjectId,
  });
  const draftProjectId =
    draftScope.key === location.key
      ? draftScope.projectId
      : initialDraftProjectId;
  const draftQuoteKey = `draft:${location.key}:${draftProjectId || "global"}`;
  const outlet = useOutlet({
    draftQuoteKey,
    draftProjectId,
    setDraftProjectId: (projectId: string) =>
      setDraftScope({ key: location.key, projectId }),
  } satisfies ChatWorkspaceContext);
  const mainRef = useRef<HTMLDivElement>(null);
  const previousPath = useRef<string | null>(null);
  const { open: leftOpen } = useChatSidebarVisibility();
  const [readingPaper, setReadingPaper] = useState(false);
  const papersPanelRef = usePanelRef();
  const listPanelWidth = useRef<number | null>(null);
  const previousPaperProject = useRef<string | null>(null);
  const quoteReceivers = useRef(new Map<string, ChatQuoteReceiver>());
  const paperOpeners = useRef(new Map<string, PaperQuoteOpener>());
  // One sidebar reader serves quoted blocks and tool-clicked entries alike.
  const entryOpeners = useRef(new Set<PaperOpen>());
  const quoteBridge = useRef({
    register: (sessionId: string, receiver: ChatQuoteReceiver) => {
      quoteReceivers.current.set(sessionId, receiver);
      return () => {
        if (quoteReceivers.current.get(sessionId) === receiver)
          quoteReceivers.current.delete(sessionId);
      };
    },
    add: (sessionId: string, reference: QuoteReference) =>
      quoteReceivers.current.get(sessionId)?.(reference) ?? false,
    registerPaperOpener: (sessionId: string, opener: PaperQuoteOpener) => {
      paperOpeners.current.set(sessionId, opener);
      return () => {
        if (paperOpeners.current.get(sessionId) === opener)
          paperOpeners.current.delete(sessionId);
      };
    },
    openPaper: (
      sessionId: string,
      reference: Extract<
        QuoteReference,
        { kind: "parsed_block" | "pdf_selection" }
      >,
    ) => {
      return paperOpeners.current.get(sessionId)?.(reference) ?? false;
    },
  }).current;
  // Exposed through the bridge so tool renderers and the citation dialog can
  // reuse the same sidebar reader that quoted blocks already open.
  const registerEntryOpener = useCallback((opener: PaperOpen) => {
    entryOpeners.current.add(opener);
    return () => {
      entryOpeners.current.delete(opener);
    };
  }, []);
  const bridge = useMemo(
    () => ({ ...quoteBridge, openEntry: registerEntryOpener }),
    [quoteBridge, registerEntryOpener],
  );
  const sessions = useQuery({
    queryKey: ["bound-sessions"],
    queryFn: () => listBoundSessions(api),
  });

  useEffect(() => {
    if (!sessions.isSuccess) return;
    const path = location.pathname;
    if (
      /^\/chat\/[^/]+\/[^/]+$/.test(path) &&
      !path.startsWith("/chat/project/") &&
      !sessions.data.some((session) => chatPath(session) === path)
    ) {
      navigate("/chat", { replace: true });
    }
  }, [location.pathname, sessions.isSuccess, sessions.data, navigate]);

  const projectRouteId = location.pathname.startsWith("/chat/project/")
    ? location.pathname.split("/")[3]
    : null;
  const activeSession = sessions.data?.find(
    (item) => chatPath(item) === location.pathname,
  );
  const isNewChat = location.pathname === "/chat/new";
  const projectId = isNewChat
    ? draftProjectId || null
    : (projectRouteId ?? activeSession?.binding.project_id ?? null);
  const papersScope =
    projectId ?? (activeSession || isNewChat ? "global" : null);

  useEffect(() => {
    if (previousPaperProject.current !== papersScope) {
      previousPaperProject.current = papersScope;
      listPanelWidth.current = null;
      setReadingPaper(false);
      return;
    }
    if (!papersScope) {
      listPanelWidth.current = null;
      setReadingPaper(false);
      return;
    }
    const frame = requestAnimationFrame(() => {
      const panel = papersPanelRef.current;
      if (!panel) return;
      if (readingPaper) {
        if (listPanelWidth.current === null)
          listPanelWidth.current = panel.getSize().inPixels;
        panel.resize("58%");
      } else if (listPanelWidth.current !== null) {
        panel.resize(listPanelWidth.current);
        listPanelWidth.current = null;
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [readingPaper, papersScope, papersPanelRef]);

  useLayoutEffect(() => {
    if (previousPath.current === null) {
      previousPath.current = location.pathname;
      return;
    }
    if (previousPath.current === location.pathname) return;
    previousPath.current = location.pathname;
    const node = mainRef.current;
    if (!node) return;
    node.classList.remove("route-page-enter");
    void node.offsetWidth;
    node.classList.add("route-page-enter");
    return () => node.classList.remove("route-page-enter");
  }, [location.pathname]);

  const main = (
    <div ref={mainRef} className="h-full min-w-0 overflow-hidden bg-background">
      {outlet}
    </div>
  );

  return (
    <ChatQuoteContext.Provider value={bridge}>
      <SidebarProvider className="min-h-0 flex-1">
        <div className="flex min-h-0 flex-1">
          <div
            aria-hidden={!leftOpen}
            inert={!leftOpen}
            className={`h-full shrink-0 overflow-hidden transition-[width,opacity] duration-(--motion-duration-normal) ease-(--motion-ease-standard) motion-reduce:transition-none ${leftOpen ? "w-(--chat-sidebar-width) opacity-100" : "w-0 opacity-0"}`}
          >
            <ChatSidebar />
          </div>
          <ResizablePanelGroup
            orientation="horizontal"
            className="min-w-0 flex-1"
          >
            <ResizablePanel minSize="24rem">{main}</ResizablePanel>
            {papersScope && (
              <>
                <ResizableHandle withHandle />
                <ResizablePanel
                  data-animated-sidebar
                  panelRef={papersPanelRef}
                  defaultSize="24rem"
                  minSize="18rem"
                  maxSize="75%"
                >
                  <ConversationPapersPanel
                    key={papersScope}
                    projectId={projectId}
                    sessionId={
                      isNewChat
                        ? draftQuoteKey
                        : (activeSession?.session.session.id ?? null)
                    }
                    onReadingChange={setReadingPaper}
                  />
                </ResizablePanel>
              </>
            )}
          </ResizablePanelGroup>
        </div>
      </SidebarProvider>
    </ChatQuoteContext.Provider>
  );
}

// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { expect, it, vi } from "vitest";

import { createQueryClient } from "@/app/query";
import {
  ChatSidebarProvider,
  useChatSidebarVisibility,
} from "@/components/providers/ChatSidebarProvider";
import { ChatPage } from "@/pages/chat/ChatPage";

vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api: {} }) }));
vi.mock("@/lib/agentSessions", () => ({
  listBoundSessions: async () => [
    {
      agentId: "agent-1",
      session: {
        session: {
          id: "session-1",
          config: { name: "测试会话" },
          created_at: "2026-10-10T00:00:00Z",
        },
      },
      binding: { project_id: null },
    },
  ],
}));
vi.mock("@/components/ui/Sidebar", () => ({
  SidebarProvider: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
vi.mock("@/components/ui/Resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizablePanel: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizableHandle: () => null,
}));
vi.mock("@/components/chat/ChatSidebar", () => ({
  ChatSidebar: () => <aside>会话侧栏</aside>,
}));
vi.mock("@/components/chat/ConversationPapersPanel", () => ({
  ConversationPapersPanel: () => <aside>项目文献</aside>,
}));

function Path() {
  return <span data-testid="path">{useLocation().pathname}</span>;
}
function Navigation() {
  const navigate = useNavigate();
  return (
    <div>
      <button onClick={() => navigate("/chat/new")}>新会话</button>
      <button onClick={() => navigate("/chat/agent-1/session-1")}>
        已有会话
      </button>
    </div>
  );
}

/** Stands in for the rail's 对话 button, which owns the fold on a conversation. */
function RailButton() {
  const { open, toggle } = useChatSidebarVisibility();
  return (
    <button onClick={toggle} aria-label={open ? "收起会话侧栏" : "展开会话侧栏"}>
      对话
    </button>
  );
}

function sessionPanel() {
  return screen.getByText("会话侧栏").parentElement!;
}

function renderChat(initialPath: string) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[initialPath]}>
        <ChatSidebarProvider>
          <RailButton />
          <Routes>
            <Route path="/chat" element={<ChatPage />}>
              <Route
                path="new"
                element={
                  <>
                    <Path />
                    新会话页面
                    <Navigation />
                  </>
                }
              />
              <Route
                path=":agentId/:sessionId"
                element={
                  <>
                    <Path />
                    会话页面
                    <Navigation />
                  </>
                }
              />
            </Route>
          </Routes>
        </ChatSidebarProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it("shows the conversation without a page toolbar of its own", async () => {
  renderChat("/chat/agent-1/session-1");
  await screen.findByText("会话侧栏");

  expect(screen.queryByRole("banner")).toBeNull();
  expect(screen.queryByRole("tablist")).toBeNull();
  expect(screen.getByTestId("path").textContent).toBe(
    "/chat/agent-1/session-1",
  );
});

it("keeps the papers panel on screen instead of offering a toggle", async () => {
  renderChat("/chat/agent-1/session-1");
  await screen.findByText("项目文献");

  expect(screen.queryByRole("button", { name: "收起文献侧栏" })).toBeNull();
  expect(screen.queryByRole("button", { name: "展开文献侧栏" })).toBeNull();
});

it("shows an empty workspace when no conversation is selected", async () => {
  renderChat("/chat");
  await screen.findByText("会话侧栏");

  expect(screen.queryByTestId("path")).toBeNull();
  expect(screen.queryByRole("banner")).toBeNull();
});

it("folds the session list from the rail button while staying on the conversation", async () => {
  renderChat("/chat/new");
  await screen.findByText("会话侧栏");
  expect(sessionPanel().hasAttribute("inert")).toBe(false);

  fireEvent.click(screen.getByRole("button", { name: "收起会话侧栏" }));
  expect(sessionPanel().hasAttribute("inert")).toBe(true);
  expect(screen.getByTestId("path").textContent).toBe("/chat/new");

  fireEvent.click(screen.getByRole("button", { name: "展开会话侧栏" }));
  expect(sessionPanel().hasAttribute("inert")).toBe(false);
});

it("switches conversations through the route", async () => {
  renderChat("/chat/new");
  await screen.findByText("会话侧栏");

  fireEvent.click(screen.getByRole("button", { name: "已有会话" }));

  await waitFor(() =>
    expect(screen.getByTestId("path").textContent).toBe(
      "/chat/agent-1/session-1",
    ),
  );
});

it("returns to the empty workspace when a requested session is unavailable", async () => {
  renderChat("/chat/agent-1/deleted");

  await waitFor(() => expect(screen.queryByTestId("path")).toBeNull());
  expect(screen.getByText("会话侧栏")).toBeTruthy();
});

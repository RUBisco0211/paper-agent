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
import { ChatPage } from "./ChatPage";

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

function renderChat(initialPath: string) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[initialPath]}>
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
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it("shows one conversation header without a tab strip when a session is open", async () => {
  renderChat("/chat/agent-1/session-1");
  await screen.findByText("测试会话");
  expect(
    screen.getByRole("banner", { name: "会话工具栏" }).textContent,
  ).toContain("测试会话");
  expect(screen.queryByRole("tablist")).toBeNull();
  expect(screen.getByRole("button", { name: "收起会话侧栏" })).toBeTruthy();
});

it("shows the papers sidebar when a global conversation is open", async () => {
  renderChat("/chat/agent-1/session-1");
  await screen.findByText("测试会话");
  expect(screen.getByText("项目文献")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "收起文献侧栏" }));
  expect(screen.getByRole("button", { name: "展开文献侧栏" })).toBeTruthy();
});

it("shows an empty workspace when no conversation is selected", async () => {
  renderChat("/chat");
  await screen.findByRole("banner", { name: "会话工具栏" });
  expect(screen.queryByTestId("path")).toBeNull();
  expect(screen.queryByRole("tablist")).toBeNull();
});

it("switches conversations through the route and keeps the sidebar toggle available", async () => {
  renderChat("/chat/new");
  fireEvent.click(screen.getByRole("button", { name: "收起会话侧栏" }));
  expect(screen.getByRole("button", { name: "展开会话侧栏" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "已有会话" }));
  await waitFor(() =>
    expect(
      screen.getByRole("banner", { name: "会话工具栏" }).textContent,
    ).toContain("测试会话"),
  );
  expect(screen.getByTestId("path").textContent).toBe(
    "/chat/agent-1/session-1",
  );
});

it("returns to the empty workspace when a requested session is unavailable", async () => {
  renderChat("/chat/agent-1/deleted");
  await waitFor(() => expect(screen.queryByTestId("path")).toBeNull());
  expect(
    screen.getByRole("banner", { name: "会话工具栏" }).textContent,
  ).toContain("对话");
});

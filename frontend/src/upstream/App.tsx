import { Navigate, createBrowserRouter, RouterProvider, useParams } from "react-router-dom"

import { RequireAuth } from "@/app/require-auth"
import { AgentUiProvider } from "@/lib/agent-ui"
import { LibraryPage } from "@/pages/library"
import { DiscoverPage } from "@/pages/discover"
import { PaperReadingPage } from "@/pages/paper-reading"
import { LoginPage } from "@/pages/login"
import { RegisterPage } from "@/pages/register"
import { AppLayout } from "@upstream/components/layout/AppLayout"
import { ModelSettingsPage } from "@upstream/pages/model-settings"
import { PaperChatPage } from "@upstream/pages/chat/PaperChatPage"
import { ChatPage } from "@upstream/pages/chat/ChatPage"
import { NewChatPage } from "@upstream/pages/chat/NewChatPage"
import { PaperCalendarPage } from "@upstream/pages/schedule/PaperCalendarPage"

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: <RequireAuth><AgentUiProvider><AppLayout /></AgentUiProvider></RequireAuth>,
    children: [
      { index: true, element: <Navigate to="/library" replace /> },
      { path: "/library", element: <main className="flex h-full min-h-0 flex-1 flex-col overflow-y-auto bg-background"><LibraryPage /></main> },
      { path: "/discover", element: <main className="flex h-full min-h-0 flex-1 flex-col overflow-y-auto bg-background"><DiscoverPage /></main> },
      { path: "/library/:paperId", element: <div className="flex h-full min-h-0 flex-1 flex-col bg-background"><PaperReadingPage /></div> },
      { path: "/projects", element: <Navigate to="/chat" replace /> },
      { path: "/projects/:projectId", element: <LegacyProjectRedirect /> },
      { path: "/calendar", element: <Navigate to="/scheduled" replace /> },
      { path: "/scheduled", element: <PaperCalendarPage /> },
      { path: "/scheduled/:scheduleId/runs/:sessionId", element: <PaperCalendarPage /> },
      { path: "/settings", element: <ModelSettingsPage /> },
      { path: "/chat", element: <ChatPage />, children: [
        { path: "new", element: <NewChatPage /> },
        { path: "project/:projectId", element: <div className="flex h-full items-center justify-center text-muted-foreground">选择会话或新建会话</div> },
        { path: ":agentId/:sessionId", element: <PaperChatPage /> },
      ] },
    ],
  },
  { path: "*", element: <Navigate to="/library" replace /> },
])

export default function App() {
  return <RouterProvider router={router} />
}

function LegacyProjectRedirect() {
  const { projectId } = useParams()
  return <Navigate to={projectId ? `/chat/project/${projectId}` : "/chat"} replace />
}

import { Navigate, createBrowserRouter, RouterProvider, useParams } from "react-router-dom"

import { RequireAuth } from "@/app/require-auth"
import { AgentUiProvider } from "@/lib/agent-ui"
import { LibraryPage } from "@/pages/library"
import { LoginPage } from "@/pages/login"
import { RegisterPage } from "@/pages/register"
import { AppLayout, SectionLayout } from "@upstream/components/layout/AppLayout"
import { ModelSettingsPage } from "@upstream/pages/model-settings"
import { PaperChatPage } from "@upstream/pages/chat/PaperChatPage"
import { ChatPage } from "@upstream/pages/chat/ChatPage"
import { PaperCalendarPage } from "@upstream/pages/schedule/PaperCalendarPage"

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: <RequireAuth><AgentUiProvider><AppLayout /></AgentUiProvider></RequireAuth>,
    children: [
      { index: true, element: <Navigate to="/library" replace /> },
      { path: "/library", element: <SectionLayout title="文献库" section="全部文献"><LibraryPage /></SectionLayout> },
      { path: "/projects", element: <Navigate to="/chat" replace /> },
      { path: "/projects/:projectId", element: <LegacyProjectRedirect /> },
      { path: "/calendar", element: <SectionLayout title="日历" section="月视图"><PaperCalendarPage /></SectionLayout> },
      { path: "/settings", element: <ModelSettingsPage /> },
      { path: "/chat", element: <ChatPage />, children: [
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

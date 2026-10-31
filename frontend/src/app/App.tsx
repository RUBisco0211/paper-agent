import { Navigate, createBrowserRouter, RouterProvider, useParams } from "react-router-dom"

import { RequireAuth } from "@/app/RequireAuth"
import { AgentUiProvider } from "@/components/providers/AgentUiProvider"
import { LibraryPage } from "@/pages/LibraryPage"
import { DiscoverPage } from "@/pages/DiscoverPage"
import { PaperReadingPage } from "@/pages/PaperReadingPage"
import { LoginPage } from "@/pages/LoginPage"
import { RegisterPage } from "@/pages/RegisterPage"
import { PasswordResetPage } from "@/pages/PasswordResetPage"
import { AppLayout } from "@/components/layout/AppLayout"
import { SettingsLayout } from "@/components/settings/SettingsLayout"
import { ModelsSection } from "@/components/settings/ModelsSection"
import { PreferencesSection } from "@/components/settings/PreferencesSection"
import { RetrievalSection } from "@/components/settings/RetrievalSection"
import { WebSearchSection } from "@/components/settings/WebSearchSection"
import { PaperChatPage } from "@/pages/chat/PaperChatPage"
import { ChatPage } from "@/pages/chat/ChatPage"
import { NewChatPage } from "@/pages/chat/NewChatPage"
import { PaperCalendarPage } from "@/pages/schedule/PaperCalendarPage"

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "/password-reset", element: <PasswordResetPage /> },
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
      { path: "/settings", element: <SettingsLayout />, children: [
        { index: true, element: <Navigate to="/settings/models" replace /> },
        { path: "models", element: <ModelsSection /> },
        { path: "retrieval", element: <RetrievalSection /> },
        { path: "web-search", element: <WebSearchSection /> },
        { path: "preferences", element: <PreferencesSection /> },
      ] },
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

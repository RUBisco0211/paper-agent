import { Navigate, createBrowserRouter, RouterProvider } from "react-router-dom"

import { RequireAuth } from "@/app/require-auth"
import { AgentUiProvider } from "@/lib/agent-ui"
import { LibraryPage } from "@/pages/library"
import { LoginPage } from "@/pages/login"
import { ProjectDetailPage } from "@/pages/project-detail"
import { ProjectsPage } from "@/pages/projects"
import { RegisterPage } from "@/pages/register"
import { AppLayout } from "@upstream/components/layout/AppLayout"
import { ModelSettingsPage } from "@upstream/pages/model-settings"
import { PaperChatPage } from "@upstream/pages/chat/PaperChatPage"

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: <RequireAuth><AgentUiProvider><AppLayout /></AgentUiProvider></RequireAuth>,
    children: [
      { index: true, element: <Navigate to="/library" replace /> },
      { path: "/library", element: <LibraryPage /> },
      { path: "/projects", element: <ProjectsPage /> },
      { path: "/projects/:projectId", element: <ProjectDetailPage /> },
      { path: "/settings", element: <ModelSettingsPage /> },
      { path: "/chat/:agentId/:sessionId", element: <PaperChatPage /> },
    ],
  },
  { path: "*", element: <Navigate to="/library" replace /> },
])

export default function App() {
  return <RouterProvider router={router} />
}

import { Navigate, createBrowserRouter } from "react-router-dom"

import { AppShell } from "@/app/app-shell"
import { RequireAuth } from "@/app/require-auth"
import { LibraryPage } from "@/pages/library"
import { LoginPage } from "@/pages/login"
import { ProjectDetailPage } from "@/pages/project-detail"
import { ProjectsPage } from "@/pages/projects"
import { SessionWorkspacePage } from "@/pages/session-workspace"
import { SessionsPage } from "@/pages/sessions"
import { RegisterPage } from "@/pages/register"
import { SettingsPage } from "@/pages/settings"

export function createAppRouter() {
  return createBrowserRouter([
    { path: "/login", element: <LoginPage /> },
    { path: "/register", element: <RegisterPage /> },
    {
      element: (
        <RequireAuth>
          <AppShell />
        </RequireAuth>
      ),
      children: [
        { index: true, element: <Navigate to="/library" replace /> },
        { path: "library", element: <LibraryPage /> },
        { path: "projects", element: <ProjectsPage /> },
        { path: "projects/:projectId", element: <ProjectDetailPage /> },
        { path: "sessions", element: <SessionsPage /> },
        { path: "sessions/:sessionId", element: <SessionWorkspacePage /> },
        { path: "settings", element: <SettingsPage /> },
      ],
    },
    {
      path: "*",
      element: (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3">
          <p className="text-lg font-medium">页面不存在</p>
          <a className="text-sm underline" href="/library">
            返回论文库
          </a>
        </div>
      ),
    },
  ])
}

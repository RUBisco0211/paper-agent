import {
  Navigate,
  createBrowserRouter,
  useRoutes,
  type RouteObject,
} from "react-router-dom"

import { AppShell } from "@/app/app-shell"
import { RequireAuth } from "@/app/require-auth"
import { LibraryPage } from "@/pages/library"
import { LoginPage } from "@/pages/login"
import { ProjectDetailPage } from "@/pages/project-detail"
import { ProjectsPage } from "@/pages/projects"
import { SessionWorkspacePage } from "@/pages/session-workspace"
import { RegisterPage } from "@/pages/register"
import { SettingsPage } from "@/pages/settings"

export function createAppRoutes(): RouteObject[] {
  return [
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
            返回文献库
          </a>
        </div>
      ),
    },
  ]
}

/** Browser router for the app; tests use the same routes in memory. */
export function createAppRouter() {
  return createBrowserRouter(createAppRoutes())
}

/** Same routes without a data router, for testing under jsdom. */
export function AppRoutes() {
  return useRoutes(createAppRoutes())
}

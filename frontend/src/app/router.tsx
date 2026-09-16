import { Navigate, createBrowserRouter } from "react-router-dom"

import { AppShell } from "@/app/app-shell"
import { RequireAuth } from "@/app/require-auth"
import { LoginPage } from "@/pages/login"
import { PlaceholderPage } from "@/pages/placeholder"
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
        {
          path: "library",
          element: (
            <PlaceholderPage
              title="论文库"
              description="上传 PDF、按标识符导入、查看处理阶段与能力。"
            />
          ),
        },
        {
          path: "projects",
          element: (
            <PlaceholderPage title="项目" description="组织个人论文库中的阅读范围。" />
          ),
        },
        {
          path: "projects/:projectId",
          element: (
            <PlaceholderPage title="项目详情" description="项目论文与会话范围。" />
          ),
        },
        {
          path: "sessions",
          element: (
            <PlaceholderPage title="会话" description="个人全库与项目范围内的问答历史。" />
          ),
        },
        {
          path: "sessions/:sessionId",
          element: (
            <PlaceholderPage title="阅读工作区" description="流式回答、工具摘要与引用核对。" />
          ),
        },
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

// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { expect, it } from "vitest"

import { SettingsLayout } from "@/components/settings/SettingsLayout"

function renderSettings() {
  render(<MemoryRouter initialEntries={["/settings/models"]}>
    <Routes>
      <Route path="/settings" element={<SettingsLayout />}>
        <Route path="models" element={<p>模型内容</p>} />
        <Route path="general" element={<p>通用内容</p>} />
      </Route>
    </Routes>
  </MemoryRouter>)
}

it("animates only the settings content when another section opens", async () => {
  renderSettings()
  expect(await screen.findByText("模型内容")).toBeTruthy()

  await userEvent.setup().click(screen.getByRole("link", { name: "通用" }))

  const content = document.querySelector('[data-slot="settings-content"]')
  const sidebar = document.querySelector('[data-slot="sidebar"]')
  expect(await screen.findByText("通用内容")).toBeTruthy()
  expect(content?.classList.contains("route-page-enter")).toBe(true)
  expect(sidebar?.classList.contains("route-page-enter")).toBe(false)
})

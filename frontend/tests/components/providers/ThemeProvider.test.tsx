// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it } from "vitest"

import { ThemeProvider, useTheme } from "@/components/providers/ThemeProvider"

/** matchMedia stub whose result and listeners the test controls. */
function stubMatchMedia(matches: boolean) {
  const listeners = new Set<() => void>()
  let current = matches
  globalThis.matchMedia = ((query: string) =>
    ({
      // 真实的 MediaQueryList 是实时读取的，桩也必须是 getter
      get matches() {
        return current
      },
      media: query,
      onchange: null,
      addEventListener: (_: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
      addListener: (listener: () => void) => listeners.add(listener),
      removeListener: (listener: () => void) => listeners.delete(listener),
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList) as typeof window.matchMedia

  return {
    emit(next: boolean) {
      current = next
      for (const listener of listeners) {
        listener()
      }
    },
    listenerCount: () => listeners.size,
  }
}

afterEach(() => {
  document.documentElement.classList.remove("dark")
  delete document.documentElement.dataset.theme
  window.localStorage.clear()
})

function ThemeSwitch() {
  const { theme, setTheme } = useTheme()
  return <button type="button" onClick={() => setTheme("solar-dusk")}>{theme}</button>
}

describe("ThemeProvider", () => {
  it("applies the dark class when the system prefers dark", () => {
    stubMatchMedia(true)

    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>,
    )

    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })

  it("keeps the class in sync when the system switches and cleans up", () => {
    const media = stubMatchMedia(false)
    const { unmount } = render(
      <ThemeProvider>
        <div />
      </ThemeProvider>,
    )
    expect(document.documentElement.classList.contains("dark")).toBe(false)

    media.emit(true)
    expect(document.documentElement.classList.contains("dark")).toBe(true)

    media.emit(false)
    expect(document.documentElement.classList.contains("dark")).toBe(false)

    expect(media.listenerCount()).toBe(1)
    unmount()
    expect(media.listenerCount()).toBe(0)
  })

  it("applies the chosen theme and keeps it in localStorage", async () => {
    stubMatchMedia(false)
    render(
      <ThemeProvider>
        <ThemeSwitch />
      </ThemeProvider>,
    )
    expect(document.documentElement.dataset.theme).toBeUndefined()

    await userEvent.setup().click(screen.getByRole("button", { name: "vintage-paper" }))

    expect(document.documentElement.dataset.theme).toBe("solar-dusk")
    expect(window.localStorage.getItem("paper-agent.theme")).toBe("solar-dusk")
    expect(screen.getByRole("button", { name: "solar-dusk" })).toBeTruthy()
  })
})

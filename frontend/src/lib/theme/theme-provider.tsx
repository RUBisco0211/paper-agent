import { useEffect, type ReactNode } from "react"

/**
 * Follows the operating system colour scheme.
 *
 * The theme is not a user preference in this product: there is no toggle and
 * nothing is persisted. `index.html` applies the class before first paint to
 * avoid a flash, and this component keeps it in sync when the system changes.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)")
    const apply = () => {
      document.documentElement.classList.toggle("dark", query.matches)
    }
    apply()
    query.addEventListener("change", apply)
    return () => query.removeEventListener("change", apply)
  }, [])

  return children
}

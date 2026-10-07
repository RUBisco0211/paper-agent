// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, expect, it, vi } from "vitest"

import { PdfViewer } from "./pdf-viewer"

const pdf = vi.hoisted(() => {
  const render = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() }))
  const getViewport = vi.fn(({ scale }: { scale: number }) => ({ width: 500 * scale, height: 700 * scale }))
  const getPage = vi.fn(async () => ({ getViewport, render }))
  const document = { numPages: 3, getPage, destroy: vi.fn(async () => {}) }
  const getDocument = vi.fn(() => ({ promise: Promise.resolve(document), destroy: vi.fn(async () => {}) }))
  return { document, getDocument, getPage, getViewport, render }
})

vi.mock("pdfjs-dist", () => ({ getDocument: pdf.getDocument, GlobalWorkerOptions: { workerSrc: "" } }))
vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api: { library: { pdfBlob: async () => new Blob(["%PDF-test"], { type: "application/pdf" }) } } }) }))

beforeEach(() => {
  pdf.getDocument.mockClear()
  pdf.getPage.mockClear()
  pdf.render.mockClear()
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as CanvasRenderingContext2D)
})

it("renders the cited PDF page in a canvas when the PDF is available", async () => {
  render(<PdfViewer paperId="paper-1" page={2} />)
  expect(await screen.findByText("2 / 3")).toBeTruthy()
  expect(pdf.getPage).toHaveBeenCalledWith(2)
  expect(screen.getByRole("img", { name: "文献原文" })).toBeTruthy()
  expect(screen.queryByTitle("文献原文")).toBeNull()
})

it("navigates and zooms within the PDF when controls are used", async () => {
  const user = userEvent.setup()
  render(<PdfViewer paperId="paper-1" page={2} />)
  await screen.findByText("2 / 3")
  await user.click(screen.getByRole("button", { name: "下一页" }))
  expect(await screen.findByText("3 / 3")).toBeTruthy()
  expect(pdf.getPage).toHaveBeenCalledWith(3)
  await user.click(screen.getByRole("button", { name: "放大" }))
  expect(await screen.findByText("125%")).toBeTruthy()
  expect(pdf.getViewport).toHaveBeenCalledWith(expect.objectContaining({ scale: 1.25 }))
})

it("marks a normalized MinerU block on a portrait PDF page", async () => {
  render(<PdfViewer paperId="paper-1" target={{
    page: 2, bbox: [100, 200, 500, 300], pageSize: [1000, 1000], coordinateSystem: "normalized",
  }} />)
  const region = await screen.findByLabelText("所选片段位置")
  expect(region.style.left).toBe("10%")
  expect(region.style.top).toBe("20%")
})

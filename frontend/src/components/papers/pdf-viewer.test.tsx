// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, expect, it, vi } from "vitest"
import { QueryClientProvider } from "@tanstack/react-query"
import { createQueryClient } from "@/app/query"
import type { ReactElement } from "react"

import { PdfViewer } from "./pdf-viewer"

const pdf = vi.hoisted(() => {
  const render = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() }))
  const getViewport = vi.fn(({ scale }: { scale: number }) => ({ width: 500 * scale, height: 700 * scale }))
  const getTextContent = vi.fn(async () => ({ items: [{ str: "Selectable PDF text" }], styles: {} }))
  const getPage = vi.fn(async () => ({ getViewport, render, getTextContent }))
  const document = { numPages: 3, getPage, destroy: vi.fn(async () => {}) }
  const getDocument = vi.fn(() => ({ promise: Promise.resolve(document), destroy: vi.fn(async () => {}) }))
  return { document, getDocument, getPage, getViewport, render, getTextContent }
})

vi.mock("pdfjs-dist", () => ({
  getDocument: pdf.getDocument,
  GlobalWorkerOptions: { workerSrc: "" },
  TextLayer: class {
    container: HTMLElement
    constructor({ container }: { container: HTMLElement }) { this.container = container }
    render() {
      const span = document.createElement("span")
      span.textContent = "Selectable PDF text"
      this.container.append(span)
      return Promise.resolve()
    }
    cancel() {}
  },
}))
const api = vi.hoisted(() => ({ library: { pdfBlob: vi.fn(async () => new Blob(["%PDF-test"], { type: "application/pdf" })) } }))
vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api }) }))

const queryClient = createQueryClient()
function renderPdf(viewer: ReactElement) {
  return render(<QueryClientProvider client={queryClient}>{viewer}</QueryClientProvider>)
}

beforeEach(() => {
  pdf.getDocument.mockClear()
  pdf.getPage.mockClear()
  pdf.render.mockClear()
  api.library.pdfBlob.mockClear()
  queryClient.clear()
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as CanvasRenderingContext2D)
})

it("renders the cited PDF page in a canvas when the PDF is available", async () => {
  renderPdf(<PdfViewer paperId="paper-1" page={2} />)
  expect(await screen.findByText("2 / 3")).toBeTruthy()
  expect(pdf.getPage).toHaveBeenCalledWith(2)
  expect(screen.getAllByRole("img", { name: "文献原文" })[1]).toBeTruthy()
  expect(screen.queryByTitle("文献原文")).toBeNull()
})

it("reuses the PDF bytes when the same paper is reopened", async () => {
  const first = renderPdf(<PdfViewer paperId="paper-1" />)
  await screen.findByText("1 / 3")
  first.unmount()
  renderPdf(<PdfViewer paperId="paper-1" />)
  await screen.findByText("1 / 3")
  expect(api.library.pdfBlob).toHaveBeenCalledTimes(1)
})

it("lays out all PDF pages in one vertical scroll area", async () => {
  renderPdf(<PdfViewer paperId="paper-1" />)
  expect(await screen.findByRole("region", { name: "PDF 页面" })).toBeTruthy()
  expect(await screen.findAllByRole("img", { name: /文献原文/ })).toHaveLength(3)
  expect(pdf.getPage).toHaveBeenCalledWith(3)
})

it("navigates and zooms within the PDF when controls are used", async () => {
  const user = userEvent.setup()
  renderPdf(<PdfViewer paperId="paper-1" page={2} />)
  await screen.findByText("2 / 3")
  await user.click(screen.getByRole("button", { name: "下一页" }))
  expect(await screen.findByText("3 / 3")).toBeTruthy()
  expect(pdf.getPage).toHaveBeenCalledWith(3)
  await user.click(screen.getByRole("button", { name: "放大" }))
  expect(await screen.findByText("125%")).toBeTruthy()
  expect(pdf.getViewport).toHaveBeenCalledWith(expect.objectContaining({ scale: 1.25 }))
})

it("marks a normalized MinerU block on a portrait PDF page", async () => {
  renderPdf(<PdfViewer paperId="paper-1" target={{
    page: 2, bbox: [100, 200, 500, 300], pageSize: [1000, 1000], coordinateSystem: "normalized",
  }} />)
  const region = await screen.findByLabelText("所选片段位置")
  expect(region.style.left).toBe("10%")
  expect(region.style.top).toBe("20%")
})

it("clears a located block from PDF whitespace without returning to the first page", async () => {
  const clear = vi.fn()
  const view = renderPdf(<PdfViewer paperId="paper-1" target={{ page: 2, bbox: [10, 20, 100, 80], pageSize: [500, 700] }} onClearTarget={clear} />)
  await screen.findByText("2 / 3")
  fireEvent.click(screen.getByRole("region", { name: "PDF 页面" }))
  expect(clear).toHaveBeenCalledOnce()
  view.rerender(<QueryClientProvider client={queryClient}><PdfViewer paperId="paper-1" onClearTarget={clear} /></QueryClientProvider>)
  expect(screen.getByText("2 / 3")).toBeTruthy()
})

it("lets the user select PDF text and copy it from the context menu", async () => {
  const user = userEvent.setup()
  renderPdf(<PdfViewer paperId="paper-1" />)
  const text = (await screen.findAllByText("Selectable PDF text"))[0]
  vi.spyOn(window, "getSelection").mockReturnValue({
    toString: () => "Selectable PDF text",
    anchorNode: text.firstChild,
    focusNode: text.firstChild,
  } as Selection)
  fireEvent.contextMenu(text, { clientX: 120, clientY: 80 })
  await user.click(await screen.findByRole("menuitem", { name: "复制" }))
  expect(await navigator.clipboard.readText()).toBe("Selectable PDF text")
})

it("zooms with a modifier wheel and scrolls horizontally with shift wheel", async () => {
  renderPdf(<PdfViewer paperId="paper-1" />)
  const region = await screen.findByRole("region", { name: "PDF 页面" })
  fireEvent.wheel(region, { ctrlKey: true, deltaY: -100 })
  expect(await screen.findByText("125%")).toBeTruthy()
  Object.defineProperty(region, "scrollLeft", { configurable: true, writable: true, value: 20 })
  fireEvent.wheel(region, { shiftKey: true, deltaY: 60 })
  expect(region.scrollLeft).toBe(80)
  fireEvent.keyDown(region, { ctrlKey: true, key: "-" })
  expect(await screen.findByText("100%")).toBeTruthy()
  fireEvent.keyDown(region, { shiftKey: true, key: "ArrowRight" })
  expect(region.scrollLeft).toBe(160)
})

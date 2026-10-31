/** Browser APIs that jsdom does not implement, needed by Radix and the chat scroller. */
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function matchMediaStub(query: string): MediaQueryList {
  return {
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  } as unknown as MediaQueryList
}

globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
globalThis.matchMedia = matchMediaStub as unknown as typeof window.matchMedia

// Radix 的浮层组件在 jsdom 下需要这些 pointer/scroll API
// （node 环境的用例没有 Element，需先判断）
if (typeof Element !== "undefined" && !Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
}
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

// ProseMirror 定位光标时需要 Range 的几何信息，jsdom 没有实现。
if (typeof Range !== "undefined" && !Range.prototype.getClientRects) {
  Range.prototype.getClientRects = () => [] as unknown as DOMRectList
  Range.prototype.getBoundingClientRect = () => new DOMRect(0, 0, 0, 0)
}
if (typeof document !== "undefined" && !document.elementFromPoint) {
  document.elementFromPoint = () => null
}

// Node 自带一个不可用的 localStorage 全局，jsdom 的 window 上反而没有实现；
// 需要持久化的用例（主题等）用这份内存实现。
if (typeof window !== "undefined" && !window.localStorage) {
  const store = new Map<string, string>()
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, String(value)) },
      removeItem: (key: string) => { store.delete(key) },
      clear: () => { store.clear() },
      key: (index: number) => [...store.keys()][index] ?? null,
      get length() { return store.size },
    },
  })
}

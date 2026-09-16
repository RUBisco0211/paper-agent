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

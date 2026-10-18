export type RenderedSelection = { start: number; end: number; text: string }

function textNodes(root: HTMLElement): Text[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) {
    const node = walker.currentNode as Text
    if (!node.parentElement?.closest('[data-quote-comment-host]')) nodes.push(node)
  }
  return nodes
}

function offsetWithin(root: HTMLElement, node: Node, offset: number): number {
  const nodes = textNodes(root)
  if (node instanceof Text) {
    let total = 0
    for (const text of nodes) {
      if (text === node) return total + offset
      total += text.length
    }
  }
  const prefix = document.createRange()
  prefix.setStart(root, 0)
  prefix.setEnd(node, offset)
  let excluded = 0
  const ignored = root.querySelectorAll('[data-quote-comment-host]')
  for (const host of ignored) if (prefix.intersectsNode(host)) excluded += host.textContent?.length ?? 0
  return prefix.toString().length - excluded
}

export function captureRenderedSelection(root: HTMLElement, range: Range): RenderedSelection | null {
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer) || range.collapsed) return null
  const start = offsetWithin(root, range.startContainer, range.startOffset)
  const end = offsetWithin(root, range.endContainer, range.endOffset)
  const text = range.toString()
  if (!text.trim() || end <= start || end - start !== text.length) return null
  return { start, end, text }
}

export function restoreRenderedSelection(root: HTMLElement, selector: RenderedSelection): Range | null {
  if (selector.start < 0 || selector.end <= selector.start || selector.end - selector.start !== selector.text.length) return null
  const nodes = textNodes(root)
  let position = 0
  let start: { node: Text; offset: number } | null = null
  let end: { node: Text; offset: number } | null = null
  for (const node of nodes) {
    const next = position + node.length
    if (!start && selector.start < next) start = { node, offset: selector.start - position }
    if (start && selector.end <= next) { end = { node, offset: selector.end - position }; break }
    position = next
  }
  if (!start || !end) return null
  const range = document.createRange()
  range.setStart(start.node, start.offset)
  range.setEnd(end.node, end.offset)
  return range.toString() === selector.text ? range : null
}

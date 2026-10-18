const name = 'paper-agent-message-quote'
const ranges = new Set<Range>()

export function addMessageHighlight(range: Range): () => void {
  if (typeof CSS === 'undefined' || !('highlights' in CSS) || typeof Highlight === 'undefined') return () => {}
  ranges.add(range)
  CSS.highlights.set(name, new Highlight(...ranges))
  return () => {
    ranges.delete(range)
    if (ranges.size) CSS.highlights.set(name, new Highlight(...ranges))
    else CSS.highlights.delete(name)
  }
}

// @vitest-environment jsdom
import { expect, it } from 'vitest'
import { captureRenderedSelection, restoreRenderedSelection } from '@/components/chat/renderedSelection'

it('locates the second repeated phrase by rendered position when markdown styling splits text nodes', () => {
  const root = document.createElement('div')
  root.innerHTML = '<p><strong>same</strong> text and same text</p>'
  document.body.append(root)
  const last = root.querySelector('p')!.lastChild!
  const range = document.createRange()
  range.setStart(last, 10)
  range.setEnd(last, 14)
  const captured = captureRenderedSelection(root, range)
  expect(captured).toEqual({ start: 14, end: 18, text: 'same' })
  expect(restoreRenderedSelection(root, captured! as { start: number; end: number; text: string })?.toString()).toBe('same')
  root.remove()
})

it('does not restore a rendered position when its text snapshot differs', () => {
  const root = document.createElement('div')
  root.textContent = 'changed content'
  expect(restoreRenderedSelection(root, { start: 0, end: 4, text: 'same' })).toBeNull()
})

it('ignores inline comment text when restoring later rendered selections', () => {
  const root = document.createElement('div')
  root.innerHTML = '<p>first</p><div data-quote-comment-host="true">a previous comment</div><p>second</p>'
  document.body.append(root)
  const range = restoreRenderedSelection(root, { start: 5, end: 11, text: 'second' })
  expect(range?.toString()).toBe('second')
  expect(captureRenderedSelection(root, range!)?.start).toBe(5)
  root.remove()
})

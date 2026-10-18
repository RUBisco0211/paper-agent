// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

import { QuoteBadge } from '@/components/chat/QuoteBadge'

it('edits a pending quote in a popover while keeping the composer compact', () => {
  const onEdit = vi.fn()
  render(<QuoteBadge reference={{ kind: 'message', source_message_id: 'm1', block_index: 0,
    start: 0, end: 4, selected_text: '原文片段', comment: '旧评论' }} onEdit={onEdit} />)

  fireEvent.click(screen.getByRole('button', { name: /编辑消息引用/ }))
  const field = screen.getByRole('textbox', { name: '编辑引用评论' })
  fireEvent.change(field, { target: { value: '新评论' } })
  fireEvent.click(screen.getByRole('button', { name: '保存评论' }))

  expect(onEdit).toHaveBeenCalledWith('新评论')
  expect(screen.queryByRole('textbox', { name: '编辑引用评论' })).toBeNull()
})

it('saves an empty comment on a pending quote', () => {
  const onEdit = vi.fn()
  render(<QuoteBadge reference={{ kind: 'message', source_message_id: 'm1', block_index: 0,
    start: 0, end: 4, selected_text: '原文片段', comment: '旧评论' }} onEdit={onEdit} />)
  fireEvent.click(screen.getByRole('button', { name: /编辑消息引用/ }))
  fireEvent.change(screen.getByRole('textbox', { name: '编辑引用评论' }), { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: '保存评论' }))
  expect(onEdit).toHaveBeenCalledWith('')
})

import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ComponentContextMenu } from './ComponentContextMenu'

it('keeps actions beside the cursor and supports keyboard navigation and dismissal', async () => {
  const user = userEvent.setup()
  const onAction = vi.fn(), onClose = vi.fn()
  render(<ComponentContextMenu clientX={window.innerWidth + 20} clientY={window.innerHeight + 20}
    label="Actuator cover" canUndo hasHidden onAction={onAction} onClose={onClose} />)
  const menu = screen.getByRole('menu', { name: 'Part actions' })
  expect(parseFloat(menu.style.left)).toBeLessThan(window.innerWidth)
  expect(parseFloat(menu.style.top)).toBeLessThan(window.innerHeight)
  expect(screen.getByRole('menuitem', { name: /Hide part/ })).toHaveFocus()
  await user.keyboard('{ArrowDown}{Enter}')
  expect(onAction).toHaveBeenCalledWith('isolate')
  expect(onClose).toHaveBeenCalled()
  onClose.mockClear()
  await user.keyboard('{Escape}')
  expect(onClose).toHaveBeenCalledOnce()
  onClose.mockClear()
  fireEvent.pointerDown(document.body)
  expect(onClose).toHaveBeenCalledOnce()
})

it('provides background recovery without a selected part', async () => {
  const user = userEvent.setup()
  const onAction = vi.fn()
  render(<ComponentContextMenu clientX={200} clientY={200} label={null} canUndo={false} hasHidden onAction={onAction} onClose={vi.fn()} />)
  expect(screen.queryByRole('menuitem', { name: /Hide part/ })).not.toBeInTheDocument()
  expect(screen.getByRole('menuitem', { name: /Undo visibility/ })).toBeDisabled()
  await user.click(screen.getByRole('menuitem', { name: /Show all/ }))
  expect(onAction).toHaveBeenCalledWith('show-all')
})

it('can dismiss an empty background menu using Escape', async () => {
  const user = userEvent.setup()
  const onClose = vi.fn()
  render(<ComponentContextMenu clientX={200} clientY={200} label={null} canUndo={false} hasHidden={false} onAction={vi.fn()} onClose={onClose} />)
  expect(screen.getByRole('menu')).toHaveFocus()
  await user.keyboard('{Escape}')
  expect(onClose).toHaveBeenCalledOnce()
})

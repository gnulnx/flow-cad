import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AnnotationOverlay } from './AnnotationOverlay'

function drawingSurface() {
  const surface = screen.getByLabelText('Viewport annotations')
  vi.spyOn(surface, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    right: 1000,
    bottom: 500,
    width: 1000,
    height: 500,
    toJSON: () => undefined,
  })
  return surface
}

function drag(surface: HTMLElement, start: [number, number], end: [number, number]) {
  fireEvent.pointerDown(surface, { button: 0, pointerId: 1, clientX: start[0], clientY: start[1] })
  fireEvent.pointerMove(surface, { pointerId: 1, clientX: end[0], clientY: end[1] })
  fireEvent.pointerUp(surface, { button: 0, pointerId: 1, clientX: end[0], clientY: end[1] })
}

describe('AnnotationOverlay', () => {
  it('does not intercept viewport pointer input while annotation is disabled', () => {
    const cameraPointer = vi.fn()
    render(<div onPointerDown={cameraPointer}><AnnotationOverlay /></div>)
    const surface = drawingSurface()
    expect(surface).toHaveAttribute('data-interactive', 'false')

    const event = new MouseEvent('pointerdown', { bubbles: true, cancelable: true })
    surface.dispatchEvent(event)
    expect(cameraPointer).toHaveBeenCalledTimes(1)
    expect(event.defaultPrevented).toBe(false)
  })

  it('draws all first-release tools and keeps markup after hide and Escape', async () => {
    const user = userEvent.setup()
    const cameraPointer = vi.fn()
    render(<div onPointerDown={cameraPointer}><AnnotationOverlay /></div>)
    const surface = drawingSurface()

    await user.click(screen.getByRole('button', { name: 'Annotate' }))
    expect(surface).toHaveAttribute('data-interactive', 'true')
    cameraPointer.mockClear()
    drag(surface, [100, 100], [300, 200])
    expect(surface.querySelectorAll('[data-mark-kind="pen"]')).toHaveLength(1)
    expect(cameraPointer).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Circle' }))
    drag(surface, [200, 100], [400, 250])
    expect(surface.querySelectorAll('[data-mark-kind="circle"]')).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: 'Arrow' }))
    drag(surface, [500, 150], [750, 300])
    expect(surface.querySelectorAll('[data-mark-kind="arrow"]')).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: 'Text' }))
    await user.type(screen.getByLabelText('Annotation text'), 'Review this clearance')
    fireEvent.pointerDown(surface, { button: 0, pointerId: 2, clientX: 600, clientY: 100 })
    expect(surface.querySelector('[data-mark-kind="text"]')).toHaveTextContent('Review this clearance')
    expect(screen.getByLabelText('4 marks')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Hide' }))
    expect(surface).toHaveAttribute('aria-hidden', 'true')
    expect(surface).toHaveAttribute('data-interactive', 'false')
    expect(screen.getByLabelText('4 marks')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Show' }))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('toolbar', { name: 'Annotation tools' })).not.toBeInTheDocument()
    expect(surface).toHaveAttribute('data-interactive', 'false')
    expect(surface.querySelectorAll('[data-mark-id]')).toHaveLength(4)
  })

  it('supports immediate undo, clear, and explicit persistence feedback', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn(async () => undefined)
    render(<AnnotationOverlay onSave={onSave} />)
    const surface = drawingSurface()
    await user.click(screen.getByRole('button', { name: 'Annotate' }))
    drag(surface, [100, 100], [300, 200])

    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(surface.querySelectorAll('[data-mark-id]')).toHaveLength(0)
    drag(surface, [200, 100], [350, 220])
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith(
      [expect.objectContaining({ kind: 'pen', intent: 'review_intent' })],
      false,
    )

    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(surface.querySelectorAll('[data-mark-id]')).toHaveLength(0)
  })
})

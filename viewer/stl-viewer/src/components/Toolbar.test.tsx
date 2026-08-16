import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Toolbar from './Toolbar'

describe('Toolbar measurement controls', () => {
  it('places menus immediately after the viewer title', () => {
    const { container } = render(
      <Toolbar
        onFitToView={vi.fn()}
        onFrameSelected={vi.fn()}
        onReload={vi.fn()}
        statusMessage="ready"
        rotationMode="turntable"
        onRotationModeChange={vi.fn()}
        onTapeModeChange={vi.fn()}
        tapeMode={false}
        onClearMeasurements={vi.fn()}
        onOpen={vi.fn()}
        markupMode={false}
        onMarkupModeToggle={vi.fn()}
        projectName="b3_robot"
      />,
    )

    const toolbar = container.querySelector('.viewer-toolbar')
    const children = Array.from(toolbar?.children ?? [])

    expect(children[0]).toHaveClass('viewer-toolbar-title')
    expect(children[1]).toHaveClass('viewer-menu')
    expect(children[2]).toHaveClass('toolbar-status')
  })

  it('opens the File menu and routes Open to file handler', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    const onTapeModeChange = vi.fn()
    const onClearMeasurements = vi.fn()

    render(
      <Toolbar
        onFitToView={vi.fn()}
        onFrameSelected={vi.fn()}
        onReload={vi.fn()}
        statusMessage="ready"
        rotationMode="turntable"
        onRotationModeChange={vi.fn()}
        onTapeModeChange={onTapeModeChange}
        tapeMode={false}
        onClearMeasurements={onClearMeasurements}
        onOpen={onOpen}
        markupMode={false}
        onMarkupModeToggle={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'File' }))
    await user.click(screen.getByRole('menuitem', { name: 'Open' }))

    expect(onOpen).toHaveBeenCalledTimes(1)
    expect(onTapeModeChange).not.toHaveBeenCalled()
    expect(onClearMeasurements).not.toHaveBeenCalled()
  })

  it('toggles annotate mode from the Edit menu', async () => {
    const user = userEvent.setup()
    const onMarkupModeToggle = vi.fn()

    render(
      <Toolbar
        onFitToView={vi.fn()}
        onFrameSelected={vi.fn()}
        onReload={vi.fn()}
        statusMessage="ready"
        rotationMode="turntable"
        onRotationModeChange={vi.fn()}
        onTapeModeChange={vi.fn()}
        tapeMode={false}
        onClearMeasurements={vi.fn()}
        onOpen={vi.fn()}
        markupMode={false}
        onMarkupModeToggle={onMarkupModeToggle}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.getByText('Ctrl+A')).toBeInTheDocument()
    await user.click(screen.getByRole('menuitem', { name: 'Annotate' }))

    expect(onMarkupModeToggle).toHaveBeenCalledTimes(1)
  })

  it('moves view commands under View menu', async () => {
    const user = userEvent.setup()
    const onFitToView = vi.fn()
    const onReload = vi.fn()
    const onFrameSelected = vi.fn()
    const onRotationModeChange = vi.fn()

    render(
      <Toolbar
        onFitToView={onFitToView}
        onFrameSelected={onFrameSelected}
        onReload={onReload}
        statusMessage="ready"
        rotationMode="turntable"
        onRotationModeChange={onRotationModeChange}
        onTapeModeChange={vi.fn()}
        tapeMode={false}
        onClearMeasurements={vi.fn()}
        onOpen={vi.fn()}
        markupMode={false}
        onMarkupModeToggle={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'View' }))
    await screen.findByRole('menu', { name: 'View menu' })
    await user.click(screen.getByRole('button', { name: 'Fit to View' }))
    expect(onFitToView).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'View' }))
    await screen.findByRole('menu', { name: 'View menu' })
    await user.click(screen.getByRole('button', { name: 'Reload' }))
    expect(onReload).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'View' }))
    await screen.findByRole('menu', { name: 'View menu' })
    await user.click(screen.getByRole('button', { name: 'Frame Selected' }))
    expect(onFrameSelected).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'View' }))
    await screen.findByRole('menu', { name: 'View menu' })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Navigation mode' }), 'free_orbit')

    expect(onRotationModeChange).toHaveBeenCalledWith('free_orbit')
  })
})

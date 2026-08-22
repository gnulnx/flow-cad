import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MeasurementOverlay, MeasurementToolButton } from './MeasurementTool'
import type { MeasurementResult } from './measurement'

const idle = { status: 'idle', featureSet: null, error: null } as const

function result(overrides: Partial<MeasurementResult> = {}): MeasurementResult {
  return {
    id: 'measurement-1',
    kind: 'distance',
    title: 'Exact vertex to Exact circle center',
    quality: 'Exact',
    startMm: [0, 0, 0],
    endMm: [3, 4, 12],
    totalMm: 13,
    deltaMm: [3, 4, 12],
    binding: {
      partUuid: 'part-1',
      artifactRevision: 'revision-1',
      featureIds: ['vertex:0', 'circle_center:0'],
    },
    hidden: false,
    pinned: false,
    offsetPx: [0, 0],
    ...overrides,
  }
}

describe('replacement MeasurementTool', () => {
  it('uses the same toggle for the obvious button and M shortcut without stealing typing', async () => {
    const user = userEvent.setup()
    const toggle = vi.fn()
    render(<><input aria-label="Editor" /><MeasurementToolButton active={false} state={idle} onToggle={toggle} /></>)

    await user.click(screen.getByRole('button', { name: 'Measure geometry' }))
    await user.keyboard('m')
    expect(toggle).toHaveBeenCalledTimes(2)

    await user.click(screen.getByRole('textbox', { name: 'Editor' }))
    await user.keyboard('m')
    expect(toggle).toHaveBeenCalledTimes(2)
  })

  it('shows exact totals and deltas, visibly marks revision drift, and exposes label controls', async () => {
    const user = userEvent.setup()
    const toggleHidden = vi.fn()
    const togglePinned = vi.fn()
    const deleteMeasurement = vi.fn()
    const clear = vi.fn()
    render(
      <MeasurementOverlay
        active={false}
        state={idle}
        hover={null}
        start={null}
        measurements={[result()]}
        currentPartUuid="part-1"
        currentArtifactRevision="revision-2"
        stageRect={null}
        onClear={clear}
        onDelete={deleteMeasurement}
        onToggleHidden={toggleHidden}
        onTogglePinned={togglePinned}
        onMove={vi.fn()}
      />,
    )

    const label = screen.getByRole('article')
    expect(within(label).getByText('13.00 mm')).toBeInTheDocument()
    expect(within(label).getByText('ΔX 3.00 mm')).toBeInTheDocument()
    expect(within(label).getByText('ΔY 4.00 mm')).toBeInTheDocument()
    expect(within(label).getByText('ΔZ 12.00 mm')).toBeInTheDocument()
    expect(within(label).getByText('Stale')).toBeInTheDocument()
    expect(label).toHaveAttribute('data-artifact-revision', 'revision-1')

    await user.click(within(label).getByRole('button', { name: 'Pin' }))
    await user.click(within(label).getByRole('button', { name: 'Hide' }))
    await user.click(within(label).getByRole('button', { name: 'Delete' }))
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(togglePinned).toHaveBeenCalledOnce()
    expect(toggleHidden).toHaveBeenCalledOnce()
    expect(deleteMeasurement).toHaveBeenCalledOnce()
    expect(clear).toHaveBeenCalledOnce()
  })

  it('labels mesh fallback hover and persisted results unmistakably Approximate', () => {
    render(
      <MeasurementOverlay
        active
        state={{ status: 'approximate', targetCount: 42 }}
        hover={{
          featureId: 'mesh_vertex:1',
          kind: 'vertex',
          quality: 'Approximate',
          label: 'Approximate vertex',
          pointMm: [1, 2, 3],
          screen: { x: 50, y: 60, depth: 0, visible: true },
          distancePx: 2,
        }}
        start={null}
        measurements={[result({ quality: 'Approximate', title: 'Approximate vertex to Approximate free point' })]}
        currentPartUuid="part-1"
        currentArtifactRevision="revision-1"
        stageRect={{ left: 0, top: 0 } as DOMRect}
        onClear={vi.fn()}
        onDelete={vi.fn()}
        onToggleHidden={vi.fn()}
        onTogglePinned={vi.fn()}
        onMove={vi.fn()}
      />,
    )

    expect(screen.getByText('Measure · Approximate')).toBeInTheDocument()
    expect(screen.getByText('Approximate vertex')).toBeInTheDocument()
    expect(screen.getByText('Approximate vertex to Approximate free point')).toBeInTheDocument()
    expect(screen.getByText('Approximate', { selector: '.quality-tag' })).toBeInTheDocument()
  })
})

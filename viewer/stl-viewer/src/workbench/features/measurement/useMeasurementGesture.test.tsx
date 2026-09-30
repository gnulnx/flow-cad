import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMeasurementGesture } from './useMeasurementGesture'
import type { MeasurementMode, SnapCandidate } from './measurement'

afterEach(() => vi.unstubAllGlobals())
function Fixture({ commit, exit, mode = 'distance', edge = false }: { commit(start: SnapCandidate, end: SnapCandidate, mode: MeasurementMode): void; exit(): void; mode?: MeasurementMode; edge?: boolean }) {
  const gesture = useMeasurementGesture({ active: true, mode, resetKey: 'part-1', commit, exit,
    snap: (x, y): SnapCandidate => ({ featureId: `point:${x}:${y}`, kind: edge ? 'line_edge' : 'vertex', quality: 'Exact', label: 'Exact vertex', pointMm: [x, y, 0], screen: { x, y, depth: 0, visible: true }, distancePx: 0,
      edge: { startMm: [0, 0, 0], endMm: [10, 0, 0], lengthMm: 10 } }),
  })
  return <div onPointerDown={gesture.onPointerDown} onPointerMove={gesture.onPointerMove} onPointerUp={gesture.onPointerUp} onPointerCancel={gesture.onPointerCancel}>
    <canvas data-testid="canvas" /><span data-testid="start">{gesture.start ? 'started' : 'idle'}</span><button>Overlay control</button>
  </div>
}
function point(type: 'pointerDown' | 'pointerUp' | 'pointerMove', x: number, y: number, target = screen.getByTestId('canvas')) {
  fireEvent[type](target, { clientX: x, clientY: y, button: 0, pointerId: 1 })
}
describe('measurement gestures', () => {
  it('supports drag and two-click distance without a third click or duplicate result', () => {
    vi.stubGlobal('PointerEvent', MouseEvent)
    const commit = vi.fn(), exit = vi.fn()
    render(<Fixture commit={commit} exit={exit} />)
    point('pointerDown', 10, 20); point('pointerMove', 30, 40); point('pointerUp', 30, 40)
    expect(commit).toHaveBeenCalledTimes(1)
    expect(commit.mock.calls[0][0].pointMm).toEqual([10, 20, 0])
    expect(commit.mock.calls[0][1].pointMm).toEqual([30, 40, 0])
    expect(screen.getByTestId('start')).toHaveTextContent('idle')
    point('pointerDown', 50, 60); point('pointerUp', 50, 60)
    expect(commit).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('start')).toHaveTextContent('started')
    point('pointerDown', 70, 80); point('pointerUp', 70, 80)
    expect(commit).toHaveBeenCalledTimes(2)
  })
  it('ignores overlay controls, cancels a start with Escape, and exits on the next Escape', () => {
    vi.stubGlobal('PointerEvent', MouseEvent)
    const commit = vi.fn(), exit = vi.fn()
    render(<Fixture commit={commit} exit={exit} />)
    point('pointerDown', 10, 10, screen.getByRole('button'))
    point('pointerUp', 20, 20, screen.getByRole('button'))
    expect(commit).not.toHaveBeenCalled()
    point('pointerDown', 10, 20); point('pointerUp', 10, 20)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.getByTestId('start')).toHaveTextContent('idle')
    expect(exit).not.toHaveBeenCalled()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(exit).toHaveBeenCalledOnce()
  })
  it('records an edge length only in edge mode', () => {
    vi.stubGlobal('PointerEvent', MouseEvent)
    const commit = vi.fn()
    render(<Fixture mode="edge_length" commit={commit} exit={vi.fn()} />)
    point('pointerDown', 10, 20); point('pointerUp', 10, 20)
    expect(commit).toHaveBeenCalledTimes(1)
    expect(commit.mock.calls[0][2]).toBe('edge_length')
  })
  it('single-clicks an edge for its length and drags from the same edge for distance by default', () => {
    vi.stubGlobal('PointerEvent', MouseEvent)
    const commit = vi.fn()
    render(<Fixture edge commit={commit} exit={vi.fn()} />)
    point('pointerDown', 10, 20); point('pointerUp', 10, 20)
    expect(commit.mock.calls[0][2]).toBe('edge_length')
    expect(screen.getByTestId('start')).toHaveTextContent('idle')
    point('pointerDown', 10, 20); point('pointerMove', 30, 40); point('pointerUp', 30, 40)
    expect(commit).toHaveBeenCalledTimes(2)
    expect(commit.mock.calls[1][2]).toBe('distance')
    expect(commit.mock.calls[1][0].pointMm).toEqual([10, 20, 0])
    expect(commit.mock.calls[1][1].pointMm).toEqual([30, 40, 0])
  })
})

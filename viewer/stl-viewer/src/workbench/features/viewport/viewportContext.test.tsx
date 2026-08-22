import { act, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MeasurementResult } from '../measurement/measurement'
import type { LiveViewportSource } from './agentScreen'
import { useViewportContextEmitter, type WorkbenchViewportContext } from './viewportContext'

afterEach(() => vi.useRealTimers())

function Harness({
  source,
  measurements,
  onChange,
}: {
  source: LiveViewportSource | null
  measurements: MeasurementResult[]
  onChange(context: WorkbenchViewportContext): void
}) {
  useViewportContextEmitter({
    getLiveViewport: () => source,
    measurements,
    annotationMarks: [],
    annotationsHidden: false,
    latestCapture: null,
    onChange,
    debounceMs: 120,
    pollMs: 100,
  })
  return null
}

describe('bounded viewport context emission', () => {
  it('debounces state and camera snapshots instead of publishing every poll', () => {
    vi.useFakeTimers()
    const onChange = vi.fn()
    const canvas = document.createElement('canvas')
    const source: LiveViewportSource = {
      canvas,
      camera: { position: [1, 2, 3], up: [0, 0, 1], quaternion: [0, 0, 0, 1], fov: 42 },
    }
    const view = render(<Harness source={source} measurements={[]} onChange={onChange} />)

    act(() => vi.advanceTimersByTime(119))
    expect(onChange).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(onChange).toHaveBeenCalledTimes(1)
    act(() => vi.advanceTimersByTime(1_000))
    expect(onChange).toHaveBeenCalledTimes(1)

    source.camera.position = [4, 5, 6]
    act(() => vi.advanceTimersByTime(220))
    expect(onChange).toHaveBeenCalledTimes(2)
    expect(onChange.mock.calls[1][0]).toMatchObject({ camera: { position: [4, 5, 6] }, measurements: [] })
    view.unmount()
  })
})

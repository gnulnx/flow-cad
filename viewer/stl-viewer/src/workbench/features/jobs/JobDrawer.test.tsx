import { act, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { createTestWorkbenchClient } from '../../testClient'
import { JobDrawer } from './JobDrawer'

describe('JobDrawer progress loop', () => {
  it('polls a watched build and reports its terminal record once', async () => {
    vi.useFakeTimers()
    const running = {
      id: 'job-1', label: 'Build guard', state: 'running' as const, phase: 'exporting', progress: 0.6,
      cancellable: true, elapsedMs: 500, lastUpdate: 'now',
    }
    const complete = { ...running, state: 'complete' as const, phase: 'complete', progress: 1, cancellable: false }
    const getJobs = vi.fn().mockResolvedValueOnce([running]).mockResolvedValue([complete])
    const client = createTestWorkbenchClient()
    client.getJobs = getJobs
    const onTerminal = vi.fn()
    render(<JobDrawer client={client} watchJobId="job-1" onWatchedJobTerminal={onTerminal} />)

    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(screen.getByText('1 active task')).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(500) })
    await act(async () => { await vi.advanceTimersByTimeAsync(500) })

    expect(onTerminal).toHaveBeenCalledOnce()
    expect(onTerminal).toHaveBeenCalledWith(complete)
    vi.useRealTimers()
  })
})

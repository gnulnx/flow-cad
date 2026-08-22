import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ExactFeatureSet } from '../../contracts'
import { createTestWorkbenchClient } from '../../testClient'
import { useExactFeatures } from './useExactFeatures'

const ready: ExactFeatureSet = {
  status: 'ready',
  partUuid: 'part-1',
  artifactRevision: 'revision-1',
  geometryAuthority: 'step_kernel',
  quality: 'exact',
  units: 'mm',
  features: [{ id: 'vertex:0', kind: 'vertex', pointMm: [0, 0, 0], source: 'step_topology', quality: 'exact' }],
  warnings: [],
  cacheHit: true,
}

describe('useExactFeatures', () => {
  it('does nothing until the selected STEP part is visible', () => {
    const lookup = vi.fn(async () => ready)
    const client = { ...createTestWorkbenchClient(), getExactFeatures: lookup }
    const { result } = renderHook(() => useExactFeatures(client, 'part-1', 'revision-1', false))

    expect(result.current.status).toBe('idle')
    expect(lookup).not.toHaveBeenCalled()
  })

  it('follows the cold 202 job contract and publishes only the warm revision result', async () => {
    const lookup = vi.fn()
      .mockResolvedValueOnce({
        status: 'job_required',
        partUuid: 'part-1',
        artifactRevision: 'revision-1',
        geometryAuthority: 'step_kernel',
        quality: 'exact',
      })
      .mockResolvedValueOnce(ready)
    const queue = vi.fn(async () => ({
      status: 'queued' as const,
      partUuid: 'part-1',
      artifactRevision: 'revision-1',
      jobId: 'job-1',
      resultUrl: '/result',
    }))
    const client = { ...createTestWorkbenchClient(), getExactFeatures: lookup, queueExactFeatures: queue }

    const { result } = renderHook(() => useExactFeatures(client, 'part-1', 'revision-1', true))

    await waitFor(() => expect(result.current.status).toBe('ready'), { timeout: 1500 })
    expect(queue).toHaveBeenCalledWith(
      'part-1',
      'revision-1',
      'exact-features:part-1:revision-1',
      expect.any(AbortSignal),
    )
    expect(result.current.featureSet).toEqual(ready)
  })

  it('stops polling and surfaces a failed extraction job', async () => {
    const cold = {
      status: 'job_required' as const,
      partUuid: 'part-1',
      artifactRevision: 'revision-1',
      geometryAuthority: 'step_kernel' as const,
      quality: 'exact' as const,
    }
    const client = {
      ...createTestWorkbenchClient({ jobs: [{
        id: 'job-1',
        label: 'Exact features',
        state: 'failed' as const,
        phase: 'extract',
        progress: null,
        cancellable: false,
        elapsedMs: 20,
        lastUpdate: 'now',
      }] }),
      getExactFeatures: vi.fn(async () => cold),
      queueExactFeatures: vi.fn(async () => ({
        status: 'queued' as const,
        partUuid: 'part-1',
        artifactRevision: 'revision-1',
        jobId: 'job-1',
        resultUrl: '/result',
      })),
    }

    const { result } = renderHook(() => useExactFeatures(client, 'part-1', 'revision-1', true))

    await waitFor(() => expect(result.current.status).toBe('failed'), { timeout: 1500 })
    expect(result.current.error).toBe('Exact STEP extraction failed: extract')
    expect(client.getExactFeatures).toHaveBeenCalledTimes(2)
  })
})

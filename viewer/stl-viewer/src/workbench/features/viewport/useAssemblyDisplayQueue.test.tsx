import { act, renderHook, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { displayBytesCache } from './displayScene'
import { useAssemblyDisplayQueue } from './useAssemblyDisplayQueue'

const part = { uuid: 'p', key: 'p', status: 'active', role: 'printable',
  occurrences: [{ id: 'p', assemblyId: 'active', translationMm: [0,0,0], rotationDeg: [0,0,0] }],
  displayArtifact: { url: '/model', contentHash: 'v1' } } as WorkbenchPart
const parts = [part]
afterEach(() => { displayBytesCache.clear(); vi.unstubAllGlobals() })
it('restores a circle-toggled part repeatedly, including StrictMode effect replay', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) })
  vi.stubGlobal('fetch', fetcher)
  const hook = renderHook(({ visible }) => useAssemblyDisplayQueue(parts, 'active', 'p', visible),
    { initialProps: { visible: ['p'] }, wrapper: StrictMode })
  await waitFor(() => expect(hook.result.current.models).toHaveLength(1))
  for (let i = 0; i < 5; i++) {
    act(() => hook.result.current.reportVisible('p'))
    hook.rerender({ visible: [] })
    expect(hook.result.current.models).toHaveLength(0)
    hook.rerender({ visible: ['p'] })
    await waitFor(() => expect(hook.result.current.models).toHaveLength(1))
    act(() => hook.result.current.reportVisible('p'))
    expect(hook.result.current.progress.visible).toBe(1)
  }
  expect(fetcher).toHaveBeenCalledTimes(1)
})

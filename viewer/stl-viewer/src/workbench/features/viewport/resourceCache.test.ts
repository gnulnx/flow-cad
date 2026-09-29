import { afterEach, describe, expect, it, vi } from 'vitest'
import { ResourceCache } from './resourceCache'
import { acquireDisplay, displayGeometryCache } from './displayGeometry'
import { displayBytesCache, loadDisplayBytes } from './displayScene'
import type { WorkbenchPart } from '../../contracts'

afterEach(() => { displayBytesCache.clear(); displayGeometryCache.clear(); vi.unstubAllGlobals() })

function triangle() {
  const bytes = new ArrayBuffer(134)
  const view = new DataView(bytes)
  view.setUint32(80, 1, true)
  view.setFloat32(108, 10, true); view.setFloat32(124, 20, true)
  return bytes
}

describe('bounded display reuse', () => {
  it('evicts the least recently used inactive resource, preserving visible leases', () => {
    const dispose = vi.fn()
    const cache = new ResourceCache<string>(20, dispose)
    const release = cache.lease('visible', 'visible', 10)
    cache.put('old', 'old', 10)
    cache.put('new', 'new', 10)
    expect(cache.get('old')).toBeUndefined()
    expect(cache.get('visible')).toBe('visible')
    expect(dispose.mock.calls).toEqual([['old']])
    release(); release()
    cache.clear()
    expect(cache.sizeBytes).toBe(0)
    expect(dispose).toHaveBeenCalledTimes(3)
  })
  it('releases oversized geometry immediately once it is no longer displayed', () => {
    const dispose = vi.fn()
    const cache = new ResourceCache<string>(10, dispose)
    const release = cache.lease('large', 'large', 20)
    expect(cache.sizeBytes).toBe(20)
    cache.clear()
    expect(dispose).not.toHaveBeenCalled()
    release()
    expect(cache.sizeBytes).toBe(0)
    expect(dispose).toHaveBeenCalledOnce()
  })
  it('shares a concurrent decode and preserves geometry across hide/restore', async () => {
    const bytes = triangle()
    const [a, b] = await Promise.all([acquireDisplay('revision1', bytes, 'stl'), acquireDisplay('revision1', bytes, 'stl')])
    expect(a.items).toBe(b.items)
    const disposed = vi.fn()
    a.items[0].geometry.addEventListener('dispose', disposed)
    a.release(); b.release()
    const restored = await acquireDisplay('revision1', bytes, 'stl')
    expect(restored.items).toBe(a.items)
    expect(disposed).not.toHaveBeenCalled()
    const changed = await acquireDisplay('revision2', bytes, 'stl')
    expect(changed.items).not.toBe(a.items)
    restored.release(); changed.release(); displayGeometryCache.clear()
    expect(disposed).toHaveBeenCalledOnce()
  })
  it('does not retain a failed decode', async () => {
    await expect(acquireDisplay('bad', new ArrayBuffer(4), 'stl')).rejects.toThrow()
    const valid = await acquireDisplay('bad', triangle(), 'stl')
    expect(valid.items).toHaveLength(1)
    valid.release()
  })
  it('restores downloaded models without HTTP, invalidating revision and project', async () => {
    const part = { uuid: 'p', displayArtifact: { url: 'http://one/model', contentHash: 'v1' } } as WorkbenchPart
    const fetcher = vi.fn().mockImplementation(async () => ({ ok: true, arrayBuffer: async () => triangle() }))
    vi.stubGlobal('fetch', fetcher)
    const signal = new AbortController().signal
    const first = await loadDisplayBytes(part, signal)
    expect(await loadDisplayBytes(part, signal)).toBe(first)
    expect(fetcher).toHaveBeenCalledTimes(1)
    await loadDisplayBytes({ ...part, displayArtifact: { ...part.displayArtifact!, contentHash: 'v2' } }, signal)
    await loadDisplayBytes({ ...part, displayArtifact: { ...part.displayArtifact!, url: 'http://two/model' } }, signal)
    expect(fetcher).toHaveBeenCalledTimes(3)
    const aborted = new AbortController(); aborted.abort()
    await expect(loadDisplayBytes(part, aborted.signal)).rejects.toThrow('Aborted')
  })
})

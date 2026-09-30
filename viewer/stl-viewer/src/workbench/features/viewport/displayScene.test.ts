import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadDisplayBytes, isSelectionClick, displayBytesCache } from './displayScene'
import { parseDisplay } from './displayGeometry'
import type { WorkbenchPart } from '../../contracts'

const part = { uuid: 'part', authorityHash: 'step-hash', displaySceneUrl: 'http://localhost/api/parts/part/display-scene',
  displayArtifact: { url: '/stl', contentHash: 'stl-hash', format: 'stl' } } as WorkbenchPart
afterEach(() => { displayBytesCache.clear(); vi.unstubAllGlobals() })

describe('component display', () => {
  it('loads cached colors and binds the actual GLB content hash', async () => {
    const bytes = new ArrayBuffer(16)
    const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'ready', sha256: 'color-hash' }) })
      .mockResolvedValueOnce({ ok: true, arrayBuffer: async () => bytes })
    vi.stubGlobal('fetch', fetcher)
    const result = await loadDisplayBytes(part, new AbortController().signal)
    expect(result).toEqual({ artifactBytes: bytes, format: 'glb', hash: 'color-hash', warning: null })
    expect(fetcher.mock.calls[1][0]).toContain('/model?artifact_revision=step-hash')
  })
  it('falls back visibly when color conversion fails', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ ok: false, status: 500, statusText: 'Broken' })
      .mockResolvedValueOnce({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) })
    vi.stubGlobal('fetch', fetcher)
    const result = await loadDisplayBytes(part, new AbortController().signal)
    expect(result.format).toBe('stl')
    expect(result.warning).toContain('Showing STL fallback')
  })
  it('does not fall back or request another file after cancellation', async () => {
    const controller = new AbortController()
    const fetcher = vi.fn().mockImplementation(() => { controller.abort(); throw new DOMException('Aborted', 'AbortError') })
    vi.stubGlobal('fetch', fetcher)
    await expect(loadDisplayBytes(part, controller.signal)).rejects.toThrow('Aborted')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it('selects a click without treating an orbit drag or measurement as selection', () => {
    expect(isSelectionClick(0, 0, false)).toBe(true)
    expect(isSelectionClick(12, 0, false)).toBe(false)
    expect(isSelectionClick(0, 2, false)).toBe(false)
    expect(isSelectionClick(0, 0, true)).toBe(false)
  })
  it('keeps STL-only input available with a neutral color', async () => {
    const data = new ArrayBuffer(84+50)
    const view = new DataView(data); view.setUint32(80, 1, true)
    view.setFloat32(84+24, 10, true); view.setFloat32(84+40, 20, true)
    const items = await parseDisplay(data, 'stl')
    expect(items).toHaveLength(1)
    expect(items[0].color.getHexString()).toBe('7792a3')
    items[0].geometry.dispose()
  })
})

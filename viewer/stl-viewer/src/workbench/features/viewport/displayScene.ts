import { ResourceCache } from './resourceCache'
import type { WorkbenchPart } from '../../contracts'

export interface DisplayBytes {
  artifactBytes: ArrayBuffer
  format: 'stl' | 'glb'
  hash: string
  warning: string | null
}

async function json(url: string, signal: AbortSignal, method = 'GET') {
  const response = await fetch(url, { signal, method })
  if (!response.ok) throw new Error(`Component colors: ${response.status} ${response.statusText}`)
  return response.json()
}

export function delay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve() }, milliseconds)
    signal.addEventListener('abort', abort, { once: true })
  })
}

export const displayBytesCache = new ResourceCache<DisplayBytes>(128 * 1024 * 1024)

function displayCacheKey(part: WorkbenchPart) {
  return JSON.stringify([part.displaySceneUrl, part.authorityHash, part.displaySceneVersion,
    part.displayArtifact?.url, part.displayArtifact?.contentHash])
}

export function cachedDisplayBytes(part: WorkbenchPart) {
  return displayBytesCache.get(displayCacheKey(part))
}

export async function loadDisplayBytes(part: WorkbenchPart, signal: AbortSignal, selected = false): Promise<DisplayBytes> {
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
  const key = displayCacheKey(part)
  const cached = displayBytesCache.get(key)
  if (cached) return cached
  const loaded = await fetchDisplayBytes(part, signal, selected)
  // Failed color conversion must be retryable; aborted callers cannot publish.
  if (!signal.aborted && !loaded.warning && !displayBytesCache.get(key)) {
    displayBytesCache.put(key, loaded, loaded.artifactBytes.byteLength)
  }
  return loaded
}

async function fetchDisplayBytes(part: WorkbenchPart, signal: AbortSignal, selected = false): Promise<DisplayBytes> {
  let warning: string | null = null
  if (part.displaySceneUrl && part.authorityHash) {
    const base = part.displaySceneUrl
    const query = `?artifact_revision=${encodeURIComponent(part.authorityHash)}`
    try {
      let scene = await json(base + query, signal)
      if (scene.status !== 'ready') {
        const queued = await json(base + '/jobs' + query + (selected ? '&selected=true' : ''), signal, 'POST')
        if (queued.status === 'ready') scene = queued
        else {
          const jobUrl = new URL(queued.job_url, base).href
          while (scene.status !== 'ready') {
            await delay(500, signal)
            const job = await json(jobUrl, signal)
            const record = job.job ?? job
            if (record.state === 'failed' || record.state === 'cancelled') {
              throw new Error(`Component colors ${record.state}: ${record.error ?? record.phase}`)
            }
            scene = await json(base + query, signal)
          }
        }
      }
      const response = await fetch(base + '/model' + query, { signal })
      if (!response.ok) throw new Error(`Component colors: ${response.status}`)
      return { artifactBytes: await response.arrayBuffer(), format: 'glb', hash: scene.sha256, warning: null }
    } catch (reason) {
      if (signal.aborted) throw reason
      warning = `${reason instanceof Error ? reason.message : 'Component colors unavailable'}. Showing STL fallback.`
    }
  }
  const response = await fetch(part.displayArtifact!.url, { signal })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return { artifactBytes: await response.arrayBuffer(), format: 'stl', hash: part.displayArtifact!.contentHash, warning }
}

export function isSelectionClick(delta: number, button: number, measureMode: boolean) {
  return !measureMode && button === 0 && delta <= 4
}

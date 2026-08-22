import { useEffect, useRef } from 'react'
import { applicationApiUrl } from '../../client'
import type { WorkbenchPart } from '../../contracts'

export interface LiveViewportSource {
  canvas: HTMLCanvasElement
  camera: {
    position: [number, number, number]
    up: [number, number, number]
    quaternion: [number, number, number, number]
    fov: number | null
  }
}

interface AgentScreenRequest {
  request_id: string
  status: 'pending'
}

interface UseAgentScreenCaptureOptions {
  enabled: boolean
  getSource(): LiveViewportSource | null
  part: WorkbenchPart | null
  backendRevision: number | null
}

export function buildAgentScreenPayload(
  requestId: string,
  source: LiveViewportSource,
  part: WorkbenchPart | null,
  backendRevision: number | null,
) {
  const dataUrl = source.canvas.toDataURL('image/png')
  if (!dataUrl.startsWith('data:image/png;base64,')) throw new Error('Live viewport did not produce a PNG capture')
  return {
    request_id: requestId,
    data_url: dataUrl,
    content_type: 'image/png',
    width: source.canvas.width,
    height: source.canvas.height,
    selected_ids: part ? [part.uuid] : [],
    visible_ids: part?.occurrenceIds ?? [],
    active_part_id: part?.uuid ?? null,
    backend_revision: backendRevision,
    rendered_artifacts: part?.displayArtifact ? [{
      part_uuid: part.uuid,
      content_hash: part.displayArtifact.contentHash,
      revision: part.displayArtifact.revision,
    }] : [],
    viewport: {
      width: source.canvas.width,
      height: source.canvas.height,
      camera: source.camera,
      render_context: 'viewport-canvas',
    },
    metadata: {
      render_context: 'viewport-canvas',
      capture_source: 'live-browser-workbench',
    },
  }
}

export function useAgentScreenCapture({ enabled, getSource, part, backendRevision }: UseAgentScreenCaptureOptions) {
  const inFlightRef = useRef(new Set<string>())

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()

    const poll = async () => {
      try {
        const response = await fetch(applicationApiUrl('/api/agent-screen/requests/latest?status=pending'), {
          signal: controller.signal,
          cache: 'no-store',
        })
        if (response.status === 404 || !response.ok) return
        const request = await response.json() as AgentScreenRequest
        if (!request.request_id || inFlightRef.current.has(request.request_id)) return
        const source = getSource()
        if (!source || source.canvas.width < 1 || source.canvas.height < 1) return
        inFlightRef.current.add(request.request_id)
        try {
          const payload = buildAgentScreenPayload(request.request_id, source, part, backendRevision)
          const capture = await fetch(applicationApiUrl('/api/agent-screen/capture'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: controller.signal,
          })
          if (!capture.ok) throw new Error(await capture.text())
        } catch (reason) {
          if (!controller.signal.aborted) {
            await fetch(applicationApiUrl(`/api/agent-screen/requests/${encodeURIComponent(request.request_id)}/fail`), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ error: reason instanceof Error ? reason.message : 'Live viewport capture failed' }),
              signal: controller.signal,
            }).catch(() => undefined)
          }
        } finally {
          inFlightRef.current.delete(request.request_id)
        }
      } catch {
        // The optional capture channel is intentionally silent while disconnected.
      }
    }

    const firstFrame = window.requestAnimationFrame(() => void poll())
    const timer = window.setInterval(() => void poll(), 1000)
    return () => {
      controller.abort()
      window.cancelAnimationFrame(firstFrame)
      window.clearInterval(timer)
    }
  }, [backendRevision, enabled, getSource, part])
}

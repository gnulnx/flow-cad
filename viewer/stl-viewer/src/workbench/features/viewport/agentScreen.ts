import { useEffect, useRef } from 'react'
import { applicationApiUrl } from '../../client'
import type { WorkbenchPart } from '../../contracts'
import { captureViewportWithAnnotations } from '../annotation/capture'

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
  getAnnotationOverlay?(): SVGSVGElement | null
  part: WorkbenchPart | null
  backendRevision: number | null
  visibleOccurrenceIds?: string[]
  renderedParts?: WorkbenchPart[]
  onCaptured?(metadata: LiveCanvasCaptureMetadata): void
}

export interface LiveCanvasCaptureMetadata {
  captureId: string
  requestId: string | null
  imageUrl: string
  contentType: string
  width: number | null
  height: number | null
  createdAt: string | null
  renderContext: 'viewport-canvas'
}

interface AgentScreenCaptureOptions {
  dataUrl?: string
  annotationOverlay?: boolean
  visibleOccurrenceIds?: string[]
  renderedParts?: WorkbenchPart[]
}

export function buildAgentScreenPayload(
  requestId: string,
  source: LiveViewportSource,
  part: WorkbenchPart | null,
  backendRevision: number | null,
  options: AgentScreenCaptureOptions = {},
) {
  const dataUrl = options.dataUrl ?? source.canvas.toDataURL('image/png')
  if (!dataUrl.startsWith('data:image/png;base64,')) throw new Error('Live viewport did not produce a PNG capture')
  return {
    request_id: requestId,
    data_url: dataUrl,
    content_type: 'image/png',
    width: source.canvas.width,
    height: source.canvas.height,
    selected_ids: part ? [part.uuid] : [],
    visible_ids: options.visibleOccurrenceIds ?? part?.occurrenceIds ?? [],
    active_part_id: part?.uuid ?? null,
    backend_revision: backendRevision,
    rendered_artifacts: (options.renderedParts ?? (part ? [part] : [])).flatMap((renderedPart) => (
      renderedPart.displayArtifact ? [{
        part_uuid: renderedPart.uuid,
        content_hash: renderedPart.displayArtifact.contentHash,
        revision: renderedPart.displayArtifact.revision,
      }] : []
    )),
    viewport: {
      width: source.canvas.width,
      height: source.canvas.height,
      camera: source.camera,
      render_context: 'viewport-canvas',
    },
    metadata: {
      render_context: 'viewport-canvas',
      capture_source: 'live-browser-workbench',
      annotation_overlay: options.annotationOverlay ?? false,
    },
  }
}

export async function captureAgentScreenPayload(
  requestId: string,
  source: LiveViewportSource,
  part: WorkbenchPart | null,
  backendRevision: number | null,
  overlay: SVGSVGElement | null,
  capture: typeof captureViewportWithAnnotations = captureViewportWithAnnotations,
  options: Pick<AgentScreenCaptureOptions, 'visibleOccurrenceIds' | 'renderedParts'> = {},
) {
  const annotationOverlay = Boolean(
    overlay
    && overlay.getAttribute('aria-hidden') !== 'true'
    && overlay.querySelector('[data-mark-id]'),
  )
  const dataUrl = await capture(source.canvas, overlay)
  return buildAgentScreenPayload(requestId, source, part, backendRevision, {
    dataUrl,
    annotationOverlay,
    ...options,
  })
}

export function liveCaptureMetadata(payload: Record<string, unknown>): LiveCanvasCaptureMetadata {
  return {
    captureId: String(payload.capture_id ?? ''),
    requestId: typeof payload.request_id === 'string' ? payload.request_id : null,
    imageUrl: String(payload.image_url ?? ''),
    contentType: String(payload.content_type ?? 'image/png'),
    width: typeof payload.width === 'number' ? payload.width : null,
    height: typeof payload.height === 'number' ? payload.height : null,
    createdAt: typeof payload.created_at === 'string' ? payload.created_at : null,
    renderContext: 'viewport-canvas',
  }
}

export function useAgentScreenCapture({ enabled, getSource, getAnnotationOverlay, part, backendRevision, visibleOccurrenceIds, renderedParts, onCaptured }: UseAgentScreenCaptureOptions) {
  const inFlightRef = useRef(new Set<string>())
  const sceneKey = `${visibleOccurrenceIds?.join('|') ?? ''}:${renderedParts?.map((item) => item.displayArtifact?.contentHash ?? '').join('|') ?? ''}`

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
          const payload = await captureAgentScreenPayload(
            request.request_id,
            source,
            part,
            backendRevision,
            getAnnotationOverlay?.() ?? null,
            captureViewportWithAnnotations,
            { visibleOccurrenceIds, renderedParts },
          )
          const capture = await fetch(applicationApiUrl('/api/agent-screen/capture'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: controller.signal,
          })
          if (!capture.ok) throw new Error(await capture.text())
          onCaptured?.(liveCaptureMetadata(await capture.json() as Record<string, unknown>))
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
  }, [backendRevision, enabled, getAnnotationOverlay, getSource, onCaptured, part, sceneKey]) // eslint-disable-line react-hooks/exhaustive-deps
}

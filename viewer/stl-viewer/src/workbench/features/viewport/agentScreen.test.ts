import { describe, expect, it, vi } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { buildAgentScreenPayload, captureAgentScreenPayload, liveCaptureMetadata } from './agentScreen'

describe('live agent-screen capture payload', () => {
  it('binds the live canvas, camera, selected occurrence, artifact, and revision', () => {
    const canvas = {
      width: 1280,
      height: 720,
      toDataURL: vi.fn(() => 'data:image/png;base64,iVBORw0KGgo='),
    } as unknown as HTMLCanvasElement
    const part: WorkbenchPart = {
      uuid: 'guard-uuid',
      key: 'unitree_l2_arch_guard',
      aliases: [],
      role: 'printable',
      status: 'active',
      artifactState: 'visible',
      geometryAuthority: 'step',
      qualityLabel: 'Exact',
      occurrenceCount: 1,
      occurrenceIds: ['guard-main'],
      occurrences: [{ assemblyId: 'active', id: 'guard-main', translationMm: [0, 0, 0], rotationDeg: [0, 0, 0] }],
      authorityHash: 'step-sha',
      displayArtifact: { contentHash: 'stl-sha', format: 'stl', url: '/api/models/stl-sha', revision: 9 },
      bounds: null,
      warnings: [],
    }
    const payload = buildAgentScreenPayload('review-one', {
      canvas,
      camera: {
        position: [120, 80, 60],
        up: [0, 0, 1],
        quaternion: [0, 0, 0, 1],
        fov: 42,
      },
    }, part, 9, {
      visibleOccurrenceIds: ['guard-main', 'chassis-main'],
      renderedParts: [part, {
        ...part,
        uuid: 'chassis-uuid',
        key: 'chassis',
        occurrenceIds: ['chassis-main'],
        occurrences: [{ assemblyId: 'active', id: 'chassis-main', translationMm: [0, 0, 0], rotationDeg: [0, 0, 0] }],
        displayArtifact: { contentHash: 'chassis-stl-sha', format: 'stl', url: '/api/models/chassis-stl-sha', revision: 9 },
      }],
    })

    expect(canvas.toDataURL).toHaveBeenCalledWith('image/png')
    expect(payload).toMatchObject({
      request_id: 'review-one',
      width: 1280,
      height: 720,
      selected_ids: ['guard-uuid'],
      visible_ids: ['guard-main', 'chassis-main'],
      backend_revision: 9,
      rendered_artifacts: [
        { part_uuid: 'guard-uuid', content_hash: 'stl-sha', revision: 9 },
        { part_uuid: 'chassis-uuid', content_hash: 'chassis-stl-sha', revision: 9 },
      ],
      viewport: { render_context: 'viewport-canvas', camera: { up: [0, 0, 1] } },
      metadata: { render_context: 'viewport-canvas', capture_source: 'live-browser-workbench', annotation_overlay: false },
    })
  })

  it('composites the visible SVG overlay into the protected live viewport capture', async () => {
    const canvas = { width: 1280, height: 720 } as HTMLCanvasElement
    const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    const mark = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    mark.setAttribute('data-mark-id', 'review-arrow')
    overlay.append(mark)
    const composite = vi.fn(async () => 'data:image/png;base64,composited')

    const payload = await captureAgentScreenPayload('review-two', {
      canvas,
      camera: {
        position: [120, 80, 60],
        up: [0, 0, 1],
        quaternion: [0, 0, 0, 1],
        fov: 42,
      },
    }, null, 10, overlay, composite)

    expect(composite).toHaveBeenCalledWith(canvas, overlay)
    expect(payload.data_url).toBe('data:image/png;base64,composited')
    expect(payload.metadata.annotation_overlay).toBe(true)
    expect(payload.viewport.render_context).toBe('viewport-canvas')
  })

  it('exposes narrow attachment metadata without carrying PNG bytes into chat context', () => {
    expect(liveCaptureMetadata({
      capture_id: 'screen-one',
      request_id: 'review-one',
      image_url: '/api/agent-screen/captures/screen-one/image',
      content_type: 'image/png',
      width: 1280,
      height: 720,
      created_at: '2026-08-22T12:00:00Z',
      viewport: { render_context: 'viewport-canvas' },
      data_url: 'must-not-leak',
    })).toEqual({
      captureId: 'screen-one',
      requestId: 'review-one',
      imageUrl: '/api/agent-screen/captures/screen-one/image',
      contentType: 'image/png',
      width: 1280,
      height: 720,
      createdAt: '2026-08-22T12:00:00Z',
      renderContext: 'viewport-canvas',
    })
  })
})

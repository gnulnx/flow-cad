import { describe, expect, it, vi } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { buildAgentScreenPayload, captureAgentScreenPayload } from './agentScreen'

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
    }, part, 9)

    expect(canvas.toDataURL).toHaveBeenCalledWith('image/png')
    expect(payload).toMatchObject({
      request_id: 'review-one',
      width: 1280,
      height: 720,
      selected_ids: ['guard-uuid'],
      visible_ids: ['guard-main'],
      backend_revision: 9,
      rendered_artifacts: [{ part_uuid: 'guard-uuid', content_hash: 'stl-sha', revision: 9 }],
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
})

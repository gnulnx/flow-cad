import { describe, expect, it } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { createAnnotationSnapshotInput } from './context'

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

describe('annotation snapshot workbench context', () => {
  it('binds a save to the current thread, live camera and viewport, selected artifact, occurrences, and backend revision', () => {
    const input = createAnnotationSnapshotInput({
      requestId: 'annotation-save-1',
      threadId: 'design-thread',
      marks: [{
        id: 'arrow-1',
        kind: 'arrow',
        points: [[0.1, 0.2], [0.8, 0.7]],
        color: '#79cbd1',
        strokeWidth: 2,
        intent: 'review_intent',
      }],
      hidden: false,
      source: {
        canvas: { width: 1280, height: 720 } as HTMLCanvasElement,
        camera: {
          position: [120, 80, 60],
          up: [0, 0, 1],
          quaternion: [0, 0, 0, 1],
          fov: 42,
        },
      },
      part,
      artifactRevision: 'step-sha',
      visibleOccurrenceIds: ['guard-main'],
      backendRevision: 9,
    })

    expect(input).toMatchObject({
      requestId: 'annotation-save-1',
      threadId: 'design-thread',
      context: {
        camera: { position: [120, 80, 60], up: [0, 0, 1], quaternion: [0, 0, 0, 1] },
        viewport: {
          width: 1280,
          height: 720,
          render_context: 'viewport-canvas',
          selected_part_uuid: 'guard-uuid',
        },
        artifactRevision: 'step-sha',
        visibleOccurrenceIds: ['guard-main'],
        viewerRevision: '9',
      },
    })
  })
})

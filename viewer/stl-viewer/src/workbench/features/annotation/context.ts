import type { WorkbenchPart } from '../../contracts'
import type { LiveViewportSource } from '../viewport/agentScreen'
import type { AnnotationMark, AnnotationSnapshotInput } from './contracts'

interface AnnotationSnapshotContextOptions {
  requestId: string
  threadId: string
  marks: AnnotationMark[]
  hidden: boolean
  source: LiveViewportSource
  part: WorkbenchPart
  artifactRevision: string
  visibleOccurrenceIds: string[]
  backendRevision: number
}

export function createAnnotationSnapshotInput({
  requestId,
  threadId,
  marks,
  hidden,
  source,
  part,
  artifactRevision,
  visibleOccurrenceIds,
  backendRevision,
}: AnnotationSnapshotContextOptions): AnnotationSnapshotInput {
  return {
    requestId,
    threadId,
    marks,
    hidden,
    context: {
      camera: source.camera,
      viewport: {
        width: source.canvas.width,
        height: source.canvas.height,
        render_context: 'viewport-canvas',
        selected_part_uuid: part.uuid,
      },
      artifactRevision,
      visibleOccurrenceIds,
      viewerRevision: String(backendRevision),
    },
  }
}

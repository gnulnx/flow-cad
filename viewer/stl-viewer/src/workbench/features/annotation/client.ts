import type { AnnotationMark, AnnotationSnapshotInput } from './contracts'

export interface SavedAnnotationEvent {
  created: boolean
  event: {
    sequence: number
    event_id: string
    thread_id: string
    event_type: 'annotation_snapshot_saved'
    snapshot: Record<string, unknown>
  }
}

export async function saveAnnotationSnapshot(
  apiBase: string,
  input: AnnotationSnapshotInput,
  signal?: AbortSignal,
): Promise<SavedAnnotationEvent> {
  const response = await fetch(
    `${apiBase.replace(/\/$/, '')}/api/annotations/threads/${encodeURIComponent(input.threadId)}/snapshots`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: input.requestId,
        hidden: input.hidden,
        marks: input.marks.map(annotationPayload),
        context: {
          camera: input.context.camera,
          viewport: input.context.viewport,
          artifact_revision: input.context.artifactRevision,
          visible_occurrence_ids: input.context.visibleOccurrenceIds,
          viewer_revision: input.context.viewerRevision,
        },
      }),
      signal,
    },
  )
  if (!response.ok) throw new Error(`Annotation save failed: ${response.status} ${await response.text()}`)
  return response.json() as Promise<SavedAnnotationEvent>
}

function annotationPayload(mark: AnnotationMark) {
  return {
    mark_id: mark.id,
    kind: mark.kind,
    points: mark.points,
    color: mark.color,
    stroke_width: mark.strokeWidth,
    text: mark.kind === 'text' ? mark.text : undefined,
    intent: mark.intent,
  }
}

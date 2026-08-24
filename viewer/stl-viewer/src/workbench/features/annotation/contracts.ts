export type AnnotationTool = 'pen' | 'circle' | 'arrow' | 'text'
export type NormalizedPoint = readonly [x: number, y: number]

interface AnnotationMarkBase {
  id: string
  color: string
  strokeWidth: number
  intent: 'review_intent'
}

export interface PenAnnotation extends AnnotationMarkBase {
  kind: 'pen'
  points: NormalizedPoint[]
}

export interface CircleAnnotation extends AnnotationMarkBase {
  kind: 'circle'
  points: [NormalizedPoint, NormalizedPoint]
}

export interface ArrowAnnotation extends AnnotationMarkBase {
  kind: 'arrow'
  points: [NormalizedPoint, NormalizedPoint]
}

export interface TextAnnotation extends AnnotationMarkBase {
  kind: 'text'
  points: [NormalizedPoint]
  text: string
}

export type AnnotationMark =
  | PenAnnotation
  | CircleAnnotation
  | ArrowAnnotation
  | TextAnnotation

export interface AnnotationContext {
  camera: Record<string, unknown>
  viewport: Record<string, unknown>
  artifactRevision: string
  visibleOccurrenceIds: string[]
  viewerRevision: string | null
}

export interface AnnotationSnapshotInput {
  requestId: string
  threadId: string
  hidden: boolean
  marks: AnnotationMark[]
  context: AnnotationContext
}

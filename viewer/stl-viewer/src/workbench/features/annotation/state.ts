import type { AnnotationMark, AnnotationTool, NormalizedPoint } from './contracts'

export const ANNOTATION_COLORS = ['#f0c983', '#79cbd1', '#e37b76', '#e9eef2'] as const

export interface AnnotationState {
  active: boolean
  visible: boolean
  tool: AnnotationTool
  color: string
  strokeWidth: number
  text: string
  marks: AnnotationMark[]
  draft: AnnotationMark | null
}

export type AnnotationAction =
  | { type: 'toggle_active' }
  | { type: 'escape' }
  | { type: 'set_tool', tool: AnnotationTool }
  | { type: 'set_color', color: string }
  | { type: 'set_text', text: string }
  | { type: 'start', id: string, point: NormalizedPoint }
  | { type: 'move', point: NormalizedPoint }
  | { type: 'finish', point: NormalizedPoint }
  | { type: 'cancel_draft' }
  | { type: 'undo' }
  | { type: 'clear' }
  | { type: 'toggle_visible' }

export function createAnnotationState(initialMarks: AnnotationMark[] = []): AnnotationState {
  return {
    active: false,
    visible: true,
    tool: 'pen',
    color: ANNOTATION_COLORS[0],
    strokeWidth: 2,
    text: '',
    marks: initialMarks,
    draft: null,
  }
}

export function annotationReducer(state: AnnotationState, action: AnnotationAction): AnnotationState {
  switch (action.type) {
    case 'toggle_active':
      return { ...state, active: !state.active, draft: null }
    case 'escape':
      return { ...state, active: false, draft: null }
    case 'set_tool':
      return { ...state, tool: action.tool, draft: null }
    case 'set_color':
      return { ...state, color: action.color }
    case 'set_text':
      return { ...state, text: action.text }
    case 'start':
      if (!state.active || !state.visible) return state
      if (state.tool === 'text') {
        const text = state.text.trim()
        if (!text) return state
        return {
          ...state,
          marks: [...state.marks, {
            id: action.id,
            kind: 'text',
            points: [action.point],
            color: state.color,
            strokeWidth: state.strokeWidth,
            intent: 'review_intent',
            text,
          }],
          text: '',
        }
      }
      if (state.tool === 'pen') {
        return {
          ...state,
          draft: {
            id: action.id,
            kind: 'pen',
            points: [action.point],
            color: state.color,
            strokeWidth: state.strokeWidth,
            intent: 'review_intent',
          },
        }
      }
      return {
        ...state,
        draft: {
          id: action.id,
          kind: state.tool,
          points: [action.point, action.point],
          color: state.color,
          strokeWidth: state.strokeWidth,
          intent: 'review_intent',
        },
      }
    case 'move':
      if (!state.draft) return state
      if (state.draft.kind === 'pen') {
        const previous = state.draft.points[state.draft.points.length - 1]
        if (previous && pointDistance(previous, action.point) < 0.001) return state
        return { ...state, draft: { ...state.draft, points: [...state.draft.points, action.point] } }
      }
      if (state.draft.kind === 'circle' || state.draft.kind === 'arrow') {
        return { ...state, draft: { ...state.draft, points: [state.draft.points[0], action.point] } }
      }
      return state
    case 'finish': {
      if (!state.draft) return state
      const moved = annotationReducer(state, { type: 'move', point: action.point })
      if (!moved.draft) return moved
      return { ...moved, marks: [...moved.marks, moved.draft], draft: null }
    }
    case 'cancel_draft':
      return { ...state, draft: null }
    case 'undo':
      if (state.draft) return { ...state, draft: null }
      return { ...state, marks: state.marks.slice(0, -1) }
    case 'clear':
      return { ...state, marks: [], draft: null }
    case 'toggle_visible':
      return { ...state, visible: !state.visible, draft: null }
  }
}

export function normalizePointer(
  clientX: number,
  clientY: number,
  bounds: Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>,
): NormalizedPoint {
  if (bounds.width <= 0 || bounds.height <= 0) return [0, 0]
  return [
    clamp((clientX - bounds.left) / bounds.width),
    clamp((clientY - bounds.top) / bounds.height),
  ]
}

function clamp(value: number) {
  return Math.max(0, Math.min(1, value))
}

function pointDistance(left: NormalizedPoint, right: NormalizedPoint) {
  return Math.hypot(left[0] - right[0], left[1] - right[1])
}

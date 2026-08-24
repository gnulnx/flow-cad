import { describe, expect, it } from 'vitest'
import { annotationReducer, createAnnotationState, normalizePointer } from './state'

describe('annotation feature state', () => {
  it('creates normalized pen, circle, arrow, and text review marks', () => {
    let state = annotationReducer(createAnnotationState(), { type: 'toggle_active' })
    state = annotationReducer(state, { type: 'start', id: 'pen-1', point: [0.1, 0.2] })
    state = annotationReducer(state, { type: 'move', point: [0.2, 0.3] })
    state = annotationReducer(state, { type: 'finish', point: [0.3, 0.4] })

    state = annotationReducer(state, { type: 'set_tool', tool: 'circle' })
    state = annotationReducer(state, { type: 'start', id: 'circle-1', point: [0.2, 0.2] })
    state = annotationReducer(state, { type: 'finish', point: [0.4, 0.5] })

    state = annotationReducer(state, { type: 'set_tool', tool: 'arrow' })
    state = annotationReducer(state, { type: 'start', id: 'arrow-1', point: [0.5, 0.5] })
    state = annotationReducer(state, { type: 'finish', point: [0.8, 0.7] })

    state = annotationReducer(state, { type: 'set_tool', tool: 'text' })
    state = annotationReducer(state, { type: 'set_text', text: 'Review this edge' })
    state = annotationReducer(state, { type: 'start', id: 'text-1', point: [0.6, 0.1] })

    expect(state.marks.map((mark) => mark.kind)).toEqual(['pen', 'circle', 'arrow', 'text'])
    expect(state.marks.every((mark) => mark.intent === 'review_intent')).toBe(true)
    expect(state.marks[0].points).toEqual([[0.1, 0.2], [0.2, 0.3], [0.3, 0.4]])
    expect(state.marks[3]).toMatchObject({ text: 'Review this edge', points: [[0.6, 0.1]] })
  })

  it('undoes, clears, hides without deleting, and Escape exits without camera state', () => {
    let state = annotationReducer(createAnnotationState(), { type: 'toggle_active' })
    state = annotationReducer(state, { type: 'start', id: 'mark-1', point: [0.1, 0.1] })
    state = annotationReducer(state, { type: 'finish', point: [0.2, 0.2] })
    state = annotationReducer(state, { type: 'toggle_visible' })
    expect(state.visible).toBe(false)
    expect(state.marks).toHaveLength(1)

    state = annotationReducer(state, { type: 'undo' })
    expect(state.marks).toHaveLength(0)
    state = annotationReducer(state, { type: 'clear' })
    state = annotationReducer(state, { type: 'escape' })
    expect(state).toMatchObject({ active: false, marks: [], draft: null })
    expect(state).not.toHaveProperty('camera')
  })

  it('clamps pointer coordinates into normalized viewport space', () => {
    const bounds = { left: 100, top: 50, width: 400, height: 200 }
    expect(normalizePointer(300, 150, bounds)).toEqual([0.5, 0.5])
    expect(normalizePointer(0, 500, bounds)).toEqual([0, 1])
  })
})

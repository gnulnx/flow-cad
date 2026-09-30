import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { componentHidden, emptyInspection, inspectComponents, inspectionShortcut, type SceneComponent } from './componentInspection'
import { useComponentInspection } from './useComponentInspection'

export const inspectionFixture: SceneComponent[] = ['Cover', 'Motor', 'Bracket'].map((label, index) => ({
  key: `component-${index}`, modelKey: 'view:revision-1', partUuid: 'view', occurrenceId: 'view-installed', label,
  context: 'Closed robot', bounds: { min: [index, 0, 0], max: [index + 1, 1, 1] },
}))

describe('component visibility behavior', () => {
  it('restores the previous partial view after isolation, and supports hiding the last part', () => {
    const hiddenCover = inspectComponents(emptyInspection, { type: 'hide', key: 'cover' })
    const isolated = inspectComponents(hiddenCover, { type: 'isolate', key: 'motor' })
    expect(componentHidden(isolated, 'motor')).toBe(false)
    expect(componentHidden(isolated, 'late-arriving-bracket')).toBe(true)
    const undone = inspectComponents(isolated, { type: 'undo' })
    expect(undone.hidden).toEqual(['cover'])
    expect(undone.isolated).toBeNull()
    const emptyView = inspectComponents(isolated, { type: 'hide', key: 'motor' })
    expect(['cover', 'motor', 'bracket'].every((key) => componentHidden(emptyView, key))).toBe(true)
    const restored = inspectComponents(emptyView, { type: 'show-all' })
    expect(restored.hidden).toEqual([])
    expect(restored.isolated).toBeNull()
  })

  it('shows a hidden part from isolation without restoring everything else', () => {
    const isolated = inspectComponents(emptyInspection, { type: 'isolate', key: 'motor' })
    const shown = inspectComponents(isolated, { type: 'show', key: 'bracket', keys: ['motor', 'bracket', 'cover'] })
    expect(shown.hidden).toEqual(['cover'])
    expect(componentHidden(shown, 'motor')).toBe(false)
    expect(componentHidden(shown, 'bracket')).toBe(false)
    expect(inspectComponents(shown, { type: 'undo' }).isolated).toBe('motor')
  })

  it('preserves visibility through inventory refreshes, but resets on view or artifact changes', () => {
    const hook = renderHook(({ components, scope }) => useComponentInspection(components, scope), {
      initialProps: { components: inspectionFixture.slice(0, 2), scope: 'closed-v1' },
    })
    act(() => hook.result.current.dispatch({ type: 'isolate', key: 'component-1' }))
    hook.rerender({ components: [...inspectionFixture], scope: 'closed-v1' })
    expect([...hook.result.current.hiddenKeys]).toEqual(['component-0', 'component-2'])
    hook.rerender({ components: inspectionFixture, scope: 'closed-v2' })
    expect(hook.result.current.hiddenKeys.size).toBe(0)
    expect(hook.result.current.state.history).toHaveLength(0)
    act(() => hook.result.current.select('component-2'))
    expect(hook.result.current.selected?.label).toBe('Bracket')
  })

  it('never consumes typing or browser shortcuts', () => {
    const key = { key: 'h', ctrlKey: false, altKey: false, metaKey: false, target: null }
    expect(inspectionShortcut(key)).toBe('hide')
    expect(inspectionShortcut({ ...key, key: 'H' })).toBe('show-all')
    expect(inspectionShortcut({ ...key, ctrlKey: true })).toBeNull()
    expect(inspectionShortcut({ ...key, target: document.createElement('input') })).toBeNull()
    const editable = document.createElement('div')
    editable.setAttribute('contenteditable', 'true')
    const span = editable.appendChild(document.createElement('span'))
    expect(inspectionShortcut({ ...key, target: span })).toBeNull()
  })
})

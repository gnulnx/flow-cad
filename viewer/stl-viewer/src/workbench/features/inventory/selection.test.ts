import { describe, expect, it } from 'vitest'
import { applyPartSelection, type PartSelectionState } from './selection'

const initial: PartSelectionState = { activePartUuid: 'body', explicitVisiblePartUuids: null }
const assembly = ['body', 'lid', 'wheel']

describe('part visibility selection', () => {
  it('uses a plain click to isolate a part and a second click to hide the sole part', () => {
    const isolated = applyPartSelection(initial, 'lid', 'replace', assembly)
    expect(isolated).toEqual({ activePartUuid: 'lid', explicitVisiblePartUuids: ['lid'] })
    expect(applyPartSelection(isolated, 'lid', 'replace', assembly)).toEqual({
      activePartUuid: null,
      explicitVisiblePartUuids: [],
    })
  })

  it('uses Ctrl or Command selection to add and remove parts from the shown set', () => {
    const lidOnly = applyPartSelection(initial, 'lid', 'replace', assembly)
    const lidAndWheel = applyPartSelection(lidOnly, 'wheel', 'toggle', assembly)
    expect(lidAndWheel).toEqual({ activePartUuid: 'wheel', explicitVisiblePartUuids: ['lid', 'wheel'] })
    expect(applyPartSelection(lidAndWheel, 'lid', 'toggle', assembly)).toEqual({
      activePartUuid: 'wheel',
      explicitVisiblePartUuids: ['wheel'],
    })
  })

  it('preserves visibility when inventory refresh only rebinds inspector focus', () => {
    const explicit = { activePartUuid: 'lid', explicitVisiblePartUuids: ['lid', 'wheel'] }
    expect(applyPartSelection(explicit, 'lid', 'focus', assembly)).toEqual(explicit)
  })
})

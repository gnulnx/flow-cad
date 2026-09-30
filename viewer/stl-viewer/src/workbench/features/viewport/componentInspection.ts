import type { Bounds3 } from '../../contracts'

/** One selectable mesh occurrence inside a loaded display artifact. */
export interface SceneComponent {
  key: string
  modelKey: string
  partUuid: string
  occurrenceId: string
  label: string
  context: string
  bounds: Bounds3
}

export interface ComponentVisibility {
  hidden: readonly string[]
  isolated: string | null
}

export interface InspectionState extends ComponentVisibility {
  selected: string | null
  history: ComponentVisibility[]
}

export const emptyInspection: InspectionState = { hidden: [], isolated: null, selected: null, history: [] }

export type InspectionAction =
  | { type: 'select'; key: string | null }
  | { type: 'hide' | 'isolate'; key: string }
  | { type: 'show'; key: string; keys: readonly string[] }
  | { type: 'show-all' | 'undo' }

export function componentHidden(state: ComponentVisibility, key: string): boolean {
  return state.hidden.includes(key) || (state.isolated !== null && state.isolated !== key)
}

export function inspectComponents(state: InspectionState, action: InspectionAction): InspectionState {
  if (action.type === 'select') return { ...state, selected: action.key }
  if (action.type === 'undo') {
    const previous = state.history[state.history.length - 1]
    return previous ? { ...state, ...previous, history: state.history.slice(0, -1) } : state
  }
  let next: ComponentVisibility
  switch (action.type) {
    case 'hide':
      if (componentHidden(state, action.key)) return state
      next = { hidden: [...state.hidden, action.key], isolated: state.isolated }
      break
    case 'isolate':
      next = { hidden: state.hidden.filter((key) => key !== action.key), isolated: action.key }
      break
    case 'show':
      if (!componentHidden(state, action.key)) return state
      // Showing one item from an isolated view preserves all other current hides.
      next = { hidden: action.keys.filter((key) => key !== action.key && componentHidden(state, key)), isolated: null }
      break
    case 'show-all':
      next = { hidden: [], isolated: null }
      break
  }
  if (next.isolated === state.isolated && next.hidden.length === state.hidden.length
    && next.hidden.every((key, index) => key === state.hidden[index])) return state
  return { ...state, ...next, history: [...state.history.slice(-49), { hidden: state.hidden, isolated: state.isolated }] }
}

export function inspectionShortcut(event: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'altKey' | 'metaKey' | 'target'>): 'hide' | 'isolate' | 'show-all' | 'undo' | null {
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]')
    || event.ctrlKey || event.altKey || event.metaKey) return null
  if (event.key === 'H') return 'show-all'
  if (event.key === 'h') return 'hide'
  if (event.key.toLowerCase() === 'i') return 'isolate'
  if (event.key.toLowerCase() === 'u') return 'undo'
  return null
}

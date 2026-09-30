import { useState } from 'react'
import type { SceneComponent } from './componentInspection'
import type { useComponentInspection } from './useComponentInspection'

interface Props {
  components: SceneComponent[]
  inspection: ReturnType<typeof useComponentInspection>
  peel: boolean
  disabled: boolean
  onPeel(active: boolean): void
  onSelect(component: SceneComponent): void
  onFrame(): void
}

export function ComponentInspector({ components, inspection, peel, disabled, onPeel, onSelect, onFrame }: Props) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState<'all' | 'hidden'>('all')
  const [query, setQuery] = useState('')
  const { selected, hiddenKeys, state, dispatch } = inspection
  const selectedVisible = selected && !hiddenKeys.has(selected.key)
  const keys = components.map((component) => component.key)
  const matches = components.filter((component) => (filter === 'all' || hiddenKeys.has(component.key))
    && `${component.label} ${component.context}`.toLowerCase().includes(query.trim().toLowerCase()))
  const showList = (next: 'all' | 'hidden') => { setOpen(true); setFilter(next) }

  return <div className="component-inspector" aria-label="View inspection">
    <div className="inspection-toolbar">
      <button type="button" className="tool-button" aria-expanded={open} aria-controls="view-components"
        onClick={() => setOpen((value) => !value)}>Parts in view ({components.length})</button>
      <button type="button" className="tool-button inspection-hidden-count" onClick={() => showList('hidden')}
        title="List and restore hidden parts">{hiddenKeys.size} hidden</button>
      <button type="button" className="tool-button" aria-pressed={peel} disabled={disabled || !components.length}
        onClick={() => onPeel(!peel)} title="Click geometry to hide it; drag still rotates. Escape exits.">Click to hide</button>
      <button type="button" className="tool-button" disabled={disabled || !selectedVisible}
        onClick={() => selected && dispatch({ type: 'hide', key: selected.key })} title="Hide selected part (H)">Hide</button>
      <button type="button" className="tool-button" disabled={disabled || !selected}
        onClick={() => selected && dispatch({ type: 'isolate', key: selected.key })} title="Show only selected part (I)">Isolate</button>
      <button type="button" className="tool-button" disabled={disabled || !state.history.length}
        onClick={() => dispatch({ type: 'undo' })} title="Undo last visibility change (U)">Undo</button>
      <button type="button" className="tool-button" disabled={disabled || (!hiddenKeys.size && !state.isolated)}
        onClick={() => dispatch({ type: 'show-all' })} title="Restore every part in this view (Shift+H)">Show all</button>
    </div>
    <div className="inspection-selection" role="status">
      {disabled ? 'Exit measurement or annotation to change visibility.' : peel ? 'Click a part to hide it. Drag to rotate. Esc exits.'
        : selected ? `Selected: ${selected.label}${hiddenKeys.has(selected.key) ? ' (hidden)' : ''}` : 'Click any part to select it, then Hide or Isolate.'}
      {!disabled && components.length > 0 && hiddenKeys.size === components.length ? ' Everything is hidden — use Show all or Undo.' : null}
    </div>
    {open ? <aside id="view-components" className="inspection-list" aria-label="Parts in loaded view">
      <div className="inspection-list__heading"><strong>Parts in this view</strong>
        <button type="button" className="tool-button" aria-label="Close parts in view" onClick={() => setOpen(false)}>×</button></div>
      <input type="search" aria-label="Search parts in view" placeholder="Find a part…" value={query} onChange={(event) => setQuery(event.target.value)} />
      <div className="segmented-control" aria-label="Filter view parts">
        <button type="button" aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>All ({components.length})</button>
        <button type="button" aria-pressed={filter === 'hidden'} onClick={() => setFilter('hidden')}>Hidden ({hiddenKeys.size})</button>
      </div>
      <div className="inspection-list__rows">
        {matches.map((component) => {
          const hidden = hiddenKeys.has(component.key)
          return <div key={component.key} className={`inspection-row${hidden ? ' inspection-row--hidden' : ''}${selected?.key === component.key ? ' inspection-row--selected' : ''}`}>
            <button type="button" className="inspection-row__name" disabled={disabled}
              aria-label={`Select ${component.label}`}
              aria-pressed={selected?.key === component.key} onClick={() => onSelect(component)} title={component.context}>
              <strong>{component.label}</strong><small>{component.context}</small>
            </button>
            <button type="button" className="tool-button" disabled={disabled} aria-label={`${hidden ? 'Show' : 'Hide'} ${component.label}`}
              onClick={() => dispatch(hidden ? { type: 'show', key: component.key, keys } : { type: 'hide', key: component.key })}>{hidden ? 'Show' : 'Hide'}</button>
          </div>
        })}
        {!matches.length ? <p>{filter === 'hidden' && !hiddenKeys.size ? 'No hidden parts.' : 'No matching parts.'}</p> : null}
      </div>
      <button type="button" className="tool-button" disabled={disabled || !selectedVisible} onClick={onFrame}>Frame selected part</button>
      <small>H hide · I isolate · U undo · Shift+H show all</small>
    </aside> : null}
  </div>
}

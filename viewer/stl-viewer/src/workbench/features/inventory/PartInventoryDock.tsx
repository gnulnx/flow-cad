import { useEffect, useMemo, useRef, useState } from 'react'
import type { ArtifactState, InventorySnapshot, WorkbenchClient, WorkbenchPart } from '../../contracts'
import type { PartSelectionMode } from './selection'

interface PartInventoryDockProps {
  client: WorkbenchClient
  activePartUuid: string | null
  visiblePartUuids?: readonly string[]
  onSelect(part: WorkbenchPart, mode: PartSelectionMode): void
  onInventoryChange?(snapshot: InventorySnapshot): void
  loadStates?: Record<string, ArtifactState>
  refreshToken?: number
}

function statusLabel(part: WorkbenchPart, loadStates: Record<string, ArtifactState>) {
  return (loadStates[part.uuid] ?? part.artifactState).replace('-', ' ')
}

export function PartInventoryDock({ client, activePartUuid, visiblePartUuids = [], onSelect, onInventoryChange, loadStates = {}, refreshToken = 0 }: PartInventoryDockProps) {
  const [snapshot, setSnapshot] = useState<InventorySnapshot | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const activePartUuidRef = useRef(activePartUuid)

  useEffect(() => {
    activePartUuidRef.current = activePartUuid
  }, [activePartUuid])

  useEffect(() => {
    const controller = new AbortController()
    client.getInventory(controller.signal).then((nextSnapshot) => {
      setSnapshot(nextSnapshot)
      onInventoryChange?.(nextSnapshot)
      setError(null)
      const refreshedSelection = activePartUuidRef.current
        ? nextSnapshot.parts.find((part) => part.uuid === activePartUuidRef.current)
        : null
      if (refreshedSelection) {
        onSelect(refreshedSelection, 'focus')
      } else if (!activePartUuidRef.current && nextSnapshot.parts.length > 0) {
        const preferred = nextSnapshot.parts.find((part) => part.status === 'active') ?? nextSnapshot.parts[0]
        onSelect(preferred, 'focus')
      }
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      setError(reason instanceof Error ? reason.message : 'Part inventory unavailable')
    })
    return () => controller.abort()
  }, [client, onInventoryChange, onSelect, refreshToken])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase()
    if (!snapshot || !normalized) return snapshot?.parts ?? []
    return snapshot.parts.filter((part) => (
      part.key.toLocaleLowerCase().includes(normalized)
      || part.aliases.some((alias) => alias.toLocaleLowerCase().includes(normalized))
      || part.role.toLocaleLowerCase().includes(normalized)
    ))
  }, [query, snapshot])

  return (
    <section className="inventory-dock" aria-labelledby="inventory-title">
      <div className="dock-heading">
        <div>
          <span className="eyebrow">Project index</span>
          <h2 id="inventory-title">Parts</h2>
        </div>
        <span className="count-badge">{snapshot?.parts.length ?? '—'}</span>
      </div>
      <label className="inventory-search">
        <span className="sr-only">Search parts</span>
        <span aria-hidden="true">⌕</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search parts or aliases"
        />
        <kbd>/</kbd>
      </label>
      <div className="inventory-summary" aria-live="polite">
        {error
          ? 'Inventory unavailable'
          : snapshot
            ? `${filtered.length} shown · revision ${snapshot.revision}`
            : 'Loading metadata…'}
      </div>
      <div className="inventory-selection-hint">Click isolates · Ctrl/Cmd-click adds or removes</div>
      <div className="inventory-list" role="listbox" aria-label="Project parts" aria-multiselectable="true">
        {error ? (
          <div className="dock-state dock-state--error">
            <strong>Could not load parts</strong>
            <span>{error}</span>
          </div>
        ) : !snapshot ? (
          Array.from({ length: 5 }, (_, index) => <div className="inventory-skeleton" key={index} />)
        ) : filtered.length === 0 ? (
          <div className="dock-state">
            <strong>No matching parts</strong>
            <span>Try a part key, alias, or role.</span>
          </div>
        ) : filtered.map((part) => {
          const displayState = loadStates[part.uuid] ?? part.artifactState
          return (
          <button
            type="button"
            role="option"
            aria-selected={visiblePartUuids.includes(part.uuid)}
            data-active={part.uuid === activePartUuid ? 'true' : 'false'}
            className="part-row"
            key={part.uuid}
            onClick={(event) => onSelect(part, event.ctrlKey || event.metaKey ? 'toggle' : 'replace')}
          >
            <span className={`artifact-state artifact-state--${displayState}`} title={statusLabel(part, loadStates)} aria-label={statusLabel(part, loadStates)} />
            <span className="part-row__identity">
              <strong>{part.key}</strong>
              <small>{part.previewOfUuid ? 'in-place preview' : part.role} · {part.occurrenceCount} occurrence{part.occurrenceCount === 1 ? '' : 's'}</small>
            </span>
            <span className={`authority-tag authority-tag--${part.geometryAuthority}`}>{part.qualityLabel}</span>
          </button>
          )
        })}
      </div>
    </section>
  )
}

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
  onShowFullyAssembled?(): void
  onBuildRobot?(): void
  buildRobotSubmitting?: boolean
  actionError?: string | null
}

function statusLabel(part: WorkbenchPart, loadStates: Record<string, ArtifactState>) {
  return (loadStates[part.uuid] ?? part.artifactState).replace('-', ' ')
}

export function PartInventoryDock({ client, activePartUuid, visiblePartUuids = [], onSelect, onInventoryChange, loadStates = {}, refreshToken = 0, onShowFullyAssembled, onBuildRobot, buildRobotSubmitting = false, actionError = null }: PartInventoryDockProps) {
  const [snapshot, setSnapshot] = useState<InventorySnapshot | null>(null)
  const [query, setQuery] = useState('')
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const activePartUuidRef = useRef(activePartUuid)
  const callbacksRef = useRef({ onSelect, onInventoryChange })

  useEffect(() => {
    activePartUuidRef.current = activePartUuid
  }, [activePartUuid])
  useEffect(() => {
    callbacksRef.current = { onSelect, onInventoryChange }
  }, [onSelect, onInventoryChange])

  useEffect(() => {
    const controller = new AbortController()
    client.getInventory(controller.signal).then((nextSnapshot) => {
      setSnapshot(nextSnapshot)
      callbacksRef.current.onInventoryChange?.(nextSnapshot)
      setError(null)
      const refreshedSelection = activePartUuidRef.current
        ? nextSnapshot.parts.find((part) => part.uuid === activePartUuidRef.current)
        : null
      if (refreshedSelection) {
        callbacksRef.current.onSelect(refreshedSelection, 'focus')
      } else if (!activePartUuidRef.current && nextSnapshot.parts.length > 0) {
        const assembly = nextSnapshot.activeAssemblyId ?? 'active'
        const preferred = nextSnapshot.parts.find((part) => part.occurrences.some((occurrence) => occurrence.assemblyId === assembly))
          ?? nextSnapshot.parts.find((part) => part.status === 'active') ?? nextSnapshot.parts[0]
        callbacksRef.current.onSelect(preferred, 'focus')
      }
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      setError(reason instanceof Error ? reason.message : 'Part inventory unavailable')
    })
    return () => controller.abort()
  }, [client, refreshToken])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase().replace(/_/g, ' ')
    if (!snapshot || !normalized) return snapshot?.parts ?? []
    return snapshot.parts.filter((part) => (
      [part.key, ...part.aliases, part.role, part.family ?? ''].some((text) =>
        text.toLocaleLowerCase().replace(/_/g, ' ').includes(normalized))
    ))
  }, [query, snapshot])
  const grouped = useMemo(() => {
    const groups = new Map<string, WorkbenchPart[]>()
    for (const part of filtered) {
      const label = part.family ?? (part.occurrenceCount > 0 ? 'Assembly' : 'Unplaced')
      groups.set(label, [...(groups.get(label) ?? []), part])
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right))
  }, [filtered])

  return (
    <section className="inventory-dock" aria-labelledby="inventory-title">
      <div className="dock-heading">
        <div>
          <span className="eyebrow">Project index</span>
          <h2 id="inventory-title">Parts</h2>
        </div>
        <span className="count-badge">{snapshot?.parts.length ?? '—'}</span>
      </div>
      <div className="inventory-primary-actions">
        <button type="button" className="tool-button tool-button--assembly" onClick={onShowFullyAssembled}>
          Show fully assembled
        </button>
        <button type="button" className="tool-button" disabled={buildRobotSubmitting} onClick={onBuildRobot}>
          {buildRobotSubmitting ? 'Submitting…' : 'Build robot'}
        </button>
        {actionError ? <span role="alert">{actionError}</span> : null}
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
      {grouped.length > 1 ? <div className="inventory-section-actions">
        <button type="button" onClick={() => setExpandedGroups(Object.fromEntries(grouped.map(([group]) => [group, true])))}>Expand all</button>
        <button type="button" onClick={() => setExpandedGroups(Object.fromEntries(grouped.map(([group]) => [group, false])))}>Collapse all</button>
      </div> : null}
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
        ) : grouped.map(([group, groupParts]) => {
          const expanded = query.trim().length > 0 || (expandedGroups[group] ?? true)
          return (
          <div className="inventory-group" role="group" aria-label={`${group} parts`} key={group}>
            <button type="button" className="inventory-group__heading" aria-expanded={expanded}
              onClick={() => setExpandedGroups((current) => ({ ...current, [group]: !expanded }))}>
              <span>{expanded ? '▾' : '▸'} {group.replace(/_/g, ' ')}</span>
              <span>{groupParts.length} parts · {groupParts.filter((part) => visiblePartUuids.includes(part.uuid)).length} shown</span>
            </button>
            {expanded ? groupParts.map((part) => {
              const displayState = loadStates[part.uuid] ?? part.artifactState
              const visible = visiblePartUuids.includes(part.uuid)
              return (
                <div
                  data-selected={visible ? 'true' : 'false'}
                  data-active={part.uuid === activePartUuid ? 'true' : 'false'}
                  className="part-row"
                  key={part.uuid}
                >
                  <button
                    type="button"
                    role="option"
                    aria-selected={visible}
                    className="part-row__select"
                    onClick={(event) => onSelect(part, event.ctrlKey || event.metaKey ? 'toggle' : 'replace')}
                  >
                    <span className={`artifact-state artifact-state--${displayState}`} title={statusLabel(part, loadStates)} aria-label={statusLabel(part, loadStates)} />
                    <span className="part-row__identity">
                      <strong title={part.key}>{part.key}</strong>
                      <small>
                        {part.previewOfUuid ? 'in-place preview' : part.role} · {part.status}
                        {part.material ? ` · ${part.material}` : ''} · {part.occurrenceCount} occurrence{part.occurrenceCount === 1 ? '' : 's'}
                      </small>
                    </span>
                    <span className={`authority-tag authority-tag--${part.geometryAuthority}`}>{part.qualityLabel}</span>
                  </button>
                  <button
                    type="button"
                    className="part-visibility-toggle"
                    aria-label={`${visible ? 'Hide' : 'Show'} ${part.key}`}
                    aria-pressed={visible}
                    onClick={(event) => {
                      event.stopPropagation()
                      onSelect(part, 'toggle')
                    }}
                  >
                    <span aria-hidden="true">{visible ? '◉' : '○'}</span>
                  </button>
                </div>
              )
            }) : null}
          </div>
        )})}
      </div>
    </section>
  )
}

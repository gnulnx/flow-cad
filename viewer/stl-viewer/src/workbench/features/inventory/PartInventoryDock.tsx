import { useEffect, useMemo, useRef, useState } from 'react'
import type { ArtifactState, InventorySnapshot, WorkbenchClient, WorkbenchPart } from '../../contracts'
import type { PartSelectionMode } from './selection'
import { PartDeleteMenu } from './PartDeleteMenu'

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

const tabs = [
  ['make', 'Parts to make'], ['purchased', 'Purchased'], ['hardware', 'Hardware'],
  ['view', 'Views'], ['reference', 'References'], ['all', 'All'],
] as const
type InventoryTab = typeof tabs[number][0]
function categoryOf(part: WorkbenchPart): string {
  return part.category ?? (part.role === 'printable' ? 'make' : part.role === 'reference' || part.role === 'legacy' ? 'reference' : 'uncategorized')
}

function statusLabel(part: WorkbenchPart, loadStates: Record<string, ArtifactState>) {
  return (loadStates[part.uuid] ?? part.artifactState).replace('-', ' ')
}

export function PartInventoryDock({ client, activePartUuid, visiblePartUuids = [], onSelect, onInventoryChange, loadStates = {}, refreshToken = 0, onShowFullyAssembled, onBuildRobot, buildRobotSubmitting = false, actionError = null }: PartInventoryDockProps) {
  const [snapshot, setSnapshot] = useState<InventorySnapshot | null>(null)
  const [query, setQuery] = useState('')
  const [tab, setTab] = useState<InventoryTab>('make')
  const [material, setMaterial] = useState('')
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const [contextMenu, setContextMenu] = useState<{ part: WorkbenchPart; x: number; y: number } | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null)
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
      } else if (nextSnapshot.parts.length > 0) {
        const assembly = nextSnapshot.activeAssemblyId ?? 'active'
        const preferred = nextSnapshot.parts.find((part) => part.occurrences.some((occurrence) => occurrence.assemblyId === assembly))
          ?? nextSnapshot.parts.find((part) => part.status === 'active') ?? nextSnapshot.parts[0]
        callbacksRef.current.onSelect(preferred, activePartUuidRef.current ? 'replace' : 'focus')
      }
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      setError(reason instanceof Error ? reason.message : 'Part inventory unavailable')
    })
    return () => controller.abort()
  }, [client, refreshToken])

  const categoryParts = useMemo(() => (snapshot?.parts ?? []).filter((part) => tab === 'all' || categoryOf(part) === tab), [snapshot, tab])
  const materials = useMemo(() => [...new Set(categoryParts.map((part) => part.material).filter((value): value is string => Boolean(value)))].sort(), [categoryParts])
  const filtered = useMemo(() => {
    const words = query.trim().toLocaleLowerCase().replace(/_/g, ' ').split(/\s+/).filter(Boolean)
    return categoryParts.filter((part) => {
      const text = [part.key, part.displayName ?? '', ...part.aliases, part.role, part.status, part.family ?? '', part.material ?? '', categoryOf(part)].join(' ').toLocaleLowerCase().replace(/_/g, ' ')
      return (material === '' || (material === '__unset' ? !part.material : part.material === material)) && words.every((word) => text.includes(word))
    })
  }, [query, categoryParts, material])
  function selectTab(nextTab: InventoryTab) {
    setTab(nextTab)
    setMaterial('')
  }
  const grouped = useMemo(() => {
    const groups = new Map<string, WorkbenchPart[]>()
    for (const part of filtered) {
      const label = part.family ?? (part.occurrenceCount > 0 ? 'Assembly' : 'Unplaced')
      groups.set(label, [...(groups.get(label) ?? []), part])
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right))
  }, [filtered])

  async function removePart(part: WorkbenchPart) {
    if (deleting) return
    setContextMenu(null)
    setDeleting(part.uuid)
    setDeleteError(null)
    setDeleteMessage(null)
    try {
      await client.deletePart(part.uuid)
      // Immediately drop the deleted row even if the following refresh fails.
      if (snapshot) {
        const next = { ...snapshot, parts: snapshot.parts.filter((p) => p.uuid !== part.uuid) }
        setSnapshot(next)
        callbacksRef.current.onInventoryChange?.(next)
      }
      const next = await client.getInventory()
      setSnapshot(next)
      callbacksRef.current.onInventoryChange?.(next)
      setDeleteMessage(`Deleted ${part.displayName ?? part.key}. Removed files are recoverable from project trash.`)
    } catch (reason: unknown) {
      setDeleteError(reason instanceof Error ? reason.message : 'Could not delete part')
    } finally {
      setDeleting(null)
    }
  }

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
      <div className="inventory-tabs" role="tablist" aria-label="Part categories">
        {tabs.map(([id, label], index) => <button key={id} type="button" role="tab"
          id={`inventory-tab-${id}`} aria-controls="inventory-panel" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1}
          onClick={() => selectTab(id)} onKeyDown={(event) => {
            const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length
              : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
                : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null
            if (next === null) return
            event.preventDefault()
            selectTab(tabs[next][0])
            document.getElementById(`inventory-tab-${tabs[next][0]}`)?.focus()
          }}>
          {label}<span>{snapshot?.parts.filter((part) => id === 'all' || categoryOf(part) === id).length ?? '—'}</span>
        </button>)}
      </div>
      <label className="inventory-search">
        <span className="sr-only">Search parts</span>
        <span aria-hidden="true">⌕</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search names, sections, materials…"
        />
        <kbd>/</kbd>
      </label>
      <label className="inventory-material">Material
        <select aria-label="Filter by material" value={material} onChange={(event) => setMaterial(event.target.value)}>
          <option value="">All materials</option>
          {materials.map((value) => <option key={value} value={value}>{value}</option>)}
          <option value="__unset">Unspecified</option>
        </select>
      </label>
      <div className="inventory-summary" aria-live="polite">
        {error
          ? 'Inventory unavailable'
          : snapshot
            ? `${filtered.length} of ${categoryParts.length} listed · ${visiblePartUuids.length} visible in scene`
            : 'Loading metadata…'}
      </div>
      <div className="inventory-selection-hint">Click isolates · Ctrl/Cmd-click adds or removes</div>
      {deleting ? <div role="status">Deleting part…</div> : null}
      {deleteError ? <div role="alert">{deleteError}</div> : null}
      {deleteMessage ? <div role="status">{deleteMessage}</div> : null}
      {contextMenu ? <PartDeleteMenu label={contextMenu.part.displayName ?? contextMenu.part.key}
        x={contextMenu.x} y={contextMenu.y} onClose={() => setContextMenu(null)}
        onDelete={() => void removePart(contextMenu.part)} /> : null}
      {grouped.length > 1 ? <div className="inventory-section-actions">
        <button type="button" onClick={() => setExpandedGroups(Object.fromEntries(grouped.map(([group]) => [group, true])))}>Expand all</button>
        <button type="button" onClick={() => setExpandedGroups(Object.fromEntries(grouped.map(([group]) => [group, false])))}>Collapse all</button>
      </div> : null}
      <div className="inventory-list" id="inventory-panel" role="tabpanel" aria-labelledby={`inventory-tab-${tab}`}><div role="listbox" aria-label="Project parts" aria-multiselectable="true">
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
            <span>Try another tab, clear filters, or search All for any part.</span>
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
                  aria-busy={deleting === part.uuid}
                  onContextMenu={(event) => {
                    event.preventDefault()
                    if (!deleting) setContextMenu({ part, x: event.clientX, y: event.clientY })
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
                      event.preventDefault()
                      const box = event.currentTarget.getBoundingClientRect()
                      if (!deleting) setContextMenu({ part, x: box.left + 20, y: box.bottom })
                    }
                  }}
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
                      <strong title={part.key}>{part.displayName ?? part.key}</strong>
                      <small>
                        {part.previewOfUuid ? 'in-place preview' : part.status}
                        {part.material ? ` · ${part.material}` : ''}
                      </small>
                    </span>
                    <span className={`authority-tag authority-tag--${part.geometryAuthority}`}>{part.qualityLabel}</span>
                  </button>
                  <button
                    type="button"
                    className="part-visibility-toggle"
                    aria-label={`${visible ? 'Hide' : 'Show'} ${part.displayName ?? part.key}`}
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
      </div></div>
    </section>
  )
}

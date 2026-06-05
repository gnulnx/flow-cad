import { useEffect, useMemo, useState } from 'react'
import { draftFromPart, type ViewerColorMode } from '../partMetadata'
import type { PartMetadataDraft, ViewerPart } from '../types'

interface ModelListProps {
  parts: ViewerPart[]
  selectedIds: string[]
  activeId: string | null
  activeVersion?: string | null
  onActivate: (partId: string, additive: boolean) => void
  metadataDrafts?: Record<string, PartMetadataDraft>
  onMetadataChange?: (partId: string, patch: Partial<PartMetadataDraft>) => void
  onMetadataReset?: (partId: string) => void
  colorMode?: ViewerColorMode
  onColorModeChange?: (mode: ViewerColorMode) => void
  collapsed: boolean
  onToggle: () => void
  width?: number
  isResizing?: boolean
}

const ACTIVE_FILTER = '__active__'
const ALL_FILTER = '__all__'

const ROLE_ORDER = ['printable', 'inspection', 'reference', 'legacy']
const ROLE_FILTERS = [
  { role: 'printable', label: 'Printable' },
  { role: 'legacy', label: 'Legacy' },
  { role: 'reference', label: 'Ref' },
  { role: 'inspection', label: 'Inspect' },
] as const

type RoleKey = typeof ROLE_FILTERS[number]['role']

const DEFAULT_ROLE_VISIBILITY: Record<RoleKey, boolean> = {
  printable: true,
  legacy: false,
  reference: false,
  inspection: false,
}

const MASS_SOURCE_OPTIONS = ['unset', 'estimated_material', 'cad_density', 'measured_scale', 'vendor_datasheet']
const COM_LABELS = ['X', 'Y', 'Z'] as const
const INERTIA_LABELS = ['IXX', 'IXY', 'IXZ', 'IYY', 'IYZ', 'IZZ'] as const

interface FamilyGroup {
  family: string
  parts: ViewerPart[]
}

interface RoleGroup {
  role: string
  families: FamilyGroup[]
}

interface VersionGroup {
  version: string
  roles: RoleGroup[]
}

function versionLabel(part: ViewerPart) {
  return part.version || 'unversioned'
}

function familyLabel(part: ViewerPart) {
  return part.family || part.module_id || 'parts'
}

function roleRank(role: string) {
  const index = ROLE_ORDER.indexOf(role)
  return index === -1 ? ROLE_ORDER.length : index
}

function roleLabel(role: string) {
  const found = ROLE_FILTERS.find((filter) => filter.role === role)
  return found?.label ?? role
}

function uniqueVersions(parts: ViewerPart[], activeVersion?: string | null) {
  const versions = Array.from(new Set(parts.map(versionLabel))).sort()
  if (activeVersion && versions.includes(activeVersion)) {
    return [activeVersion, ...versions.filter((version) => version !== activeVersion)]
  }
  return versions
}

function groupParts(parts: ViewerPart[], activeVersion?: string | null): VersionGroup[] {
  const versions = uniqueVersions(parts, activeVersion)
  return versions
    .map((version) => {
      const versionParts = parts.filter((part) => versionLabel(part) === version)
      const roles = Array.from(new Set(versionParts.map((part) => part.role)))
        .sort((a, b) => roleRank(a) - roleRank(b) || a.localeCompare(b))
        .map((role) => {
          const roleParts = versionParts.filter((part) => part.role === role)
          const families = Array.from(new Set(roleParts.map(familyLabel)))
            .sort()
            .map((family) => ({
              family,
              parts: roleParts
                .filter((part) => familyLabel(part) === family)
                .sort((a, b) => Number(b.default_visible) - Number(a.default_visible) || a.id.localeCompare(b.id)),
            }))
          return { role, families }
        })
      return { version, roles }
    })
    .filter((group) => group.roles.some((role) => role.families.some((family) => family.parts.length > 0)))
}

function replaceTupleValue<T extends readonly string[]>(values: T, index: number, value: string): T {
  const next = [...values]
  next[index] = value
  return next as unknown as T
}

function joinedList(values: readonly string[]) {
  return values.length ? values.join(', ') : 'none'
}

function colorPickerValue(value: string) {
  return /^#[0-9a-fA-F]{6}$/.test(value.trim()) ? value : '#5ec4ff'
}

function PartDetails({
  part,
  draft,
  onChange,
  onReset,
}: {
  part: ViewerPart
  draft: PartMetadataDraft
  onChange?: (patch: Partial<PartMetadataDraft>) => void
  onReset?: () => void
}) {
  const editable = Boolean(onChange)
  return (
    <div className="part-details" onClick={(event) => event.stopPropagation()}>
      <div className="part-detail-grid">
        <label className="part-detail-field">
          <span>Material</span>
          <input
            aria-label={`${part.id} material`}
            value={draft.material}
            disabled={!editable}
            onChange={(event) => onChange?.({ material: event.target.value })}
          />
        </label>
        <label className="part-detail-field">
          <span>Color</span>
          <div className="part-color-field">
            <input
              type="color"
              aria-label={`${part.id} color picker`}
              value={colorPickerValue(draft.display_color)}
              disabled={!editable}
              onChange={(event) => onChange?.({ display_color: event.target.value })}
            />
            <input
              aria-label={`${part.id} display color`}
              value={draft.display_color}
              disabled={!editable}
              onChange={(event) => onChange?.({ display_color: event.target.value })}
            />
          </div>
        </label>
        <label className="part-detail-field">
          <span>Mass kg</span>
          <input
            type="number"
            aria-label={`${part.id} mass kg`}
            min="0"
            step="0.001"
            value={draft.mass_kg}
            disabled={!editable}
            onChange={(event) => onChange?.({ mass_kg: event.target.value })}
          />
        </label>
        <label className="part-detail-field">
          <span>Mass source</span>
          <select
            aria-label={`${part.id} mass source`}
            value={draft.mass_source}
            disabled={!editable}
            onChange={(event) => onChange?.({ mass_source: event.target.value })}
          >
            {MASS_SOURCE_OPTIONS.includes(draft.mass_source) ? null : (
              <option value={draft.mass_source}>{draft.mass_source}</option>
            )}
            {MASS_SOURCE_OPTIONS.map((source) => (
              <option key={source} value={source}>{source}</option>
            ))}
          </select>
        </label>
        <div className="part-detail-field part-detail-wide">
          <span>COM mm</span>
          <div className="part-vector-inputs part-vector-3">
            {COM_LABELS.map((label, index) => (
              <input
                key={label}
                type="number"
                step="0.1"
                aria-label={`${part.id} COM ${label}`}
                placeholder={label}
                value={draft.center_of_mass_mm[index]}
                disabled={!editable}
                onChange={(event) => onChange?.({
                  center_of_mass_mm: replaceTupleValue(draft.center_of_mass_mm, index, event.target.value),
                })}
              />
            ))}
          </div>
        </div>
        <div className="part-detail-field part-detail-wide">
          <span>Inertia kg m2</span>
          <div className="part-vector-inputs part-vector-6">
            {INERTIA_LABELS.map((label, index) => (
              <input
                key={label}
                type="number"
                step="0.000001"
                aria-label={`${part.id} inertia ${label}`}
                placeholder={label}
                value={draft.inertia_kg_m2[index]}
                disabled={!editable}
                onChange={(event) => onChange?.({
                  inertia_kg_m2: replaceTupleValue(draft.inertia_kg_m2, index, event.target.value),
                })}
              />
            ))}
          </div>
        </div>
      </div>
      <dl className="part-readonly-details">
        <div>
          <dt>Version</dt>
          <dd>{versionLabel(part)}</dd>
        </div>
        <div>
          <dt>Role</dt>
          <dd>{roleLabel(part.role)}</dd>
        </div>
        <div>
          <dt>Family</dt>
          <dd>{familyLabel(part)}</dd>
        </div>
        <div>
          <dt>Artifact</dt>
          <dd>{part.artifact_format ?? 'missing'}</dd>
        </div>
        <div>
          <dt>Assembly IDs</dt>
          <dd>{joinedList(part.assembly_ids)}</dd>
        </div>
        <div>
          <dt>Compatible</dt>
          <dd>{joinedList(part.compatible_versions)}</dd>
        </div>
        <div>
          <dt>Occurrences</dt>
          <dd>{part.occurrences.map((occurrence) => occurrence.name).join(', ') || 'none'}</dd>
        </div>
      </dl>
      {editable && onReset ? (
        <div className="part-detail-actions">
          <button type="button" className="part-detail-reset" onClick={onReset}>Reset</button>
        </div>
      ) : null}
    </div>
  )
}

export default function ModelList({
  parts,
  selectedIds,
  activeId,
  activeVersion,
  onActivate,
  metadataDrafts = {},
  onMetadataChange,
  onMetadataReset,
  colorMode = 'workbench',
  onColorModeChange,
  collapsed,
  onToggle,
  width,
  isResizing,
}: ModelListProps) {
  const versions = useMemo(() => uniqueVersions(parts, activeVersion), [activeVersion, parts])
  const [versionFilter, setVersionFilter] = useState(ACTIVE_FILTER)
  const [roleVisibility, setRoleVisibility] = useState(DEFAULT_ROLE_VISIBILITY)
  const [expandedIds, setExpandedIds] = useState<string[]>([])

  useEffect(() => {
    setVersionFilter(ACTIVE_FILTER)
  }, [activeVersion])

  useEffect(() => {
    const partIds = new Set(parts.map((part) => part.id))
    setExpandedIds((current) => current.filter((id) => partIds.has(id)))
  }, [parts])

  const visibleParts = useMemo(() => {
    const resolvedVersion = versionFilter === ACTIVE_FILTER ? activeVersion : versionFilter
    return parts.filter((part) => {
      if (resolvedVersion && resolvedVersion !== ALL_FILTER && versionLabel(part) !== resolvedVersion) return false
      const role = part.role as RoleKey
      return roleVisibility[role] ?? true
    })
  }, [activeVersion, parts, roleVisibility, versionFilter])
  const groups = useMemo(() => groupParts(visibleParts, activeVersion), [activeVersion, visibleParts])

  const toggleRole = (role: RoleKey) => {
    setRoleVisibility((current) => ({ ...current, [role]: !current[role] }))
  }

  const toggleExpanded = (partId: string) => {
    setExpandedIds((current) => (
      current.includes(partId)
        ? current.filter((id) => id !== partId)
        : [...current, partId]
    ))
  }

  const openSelectedDetails = () => {
    setExpandedIds((current) => Array.from(new Set([...current, ...selectedIds])))
  }

  if (parts.length === 0) return null

  return (
    <div 
      className={`sidebar-dock right-dock ${collapsed ? 'collapsed' : ''} ${isResizing ? 'resizing' : ''}`}
      style={{ width: collapsed ? undefined : width }}
    >
      <div className="sidebar-icon-strip" onClick={onToggle} title="Expand Parts Panel">
        <button type="button" className="icon-strip-btn">⚙️</button>
        <div style={{
          writingMode: 'vertical-lr',
          textTransform: 'uppercase',
          fontSize: '11px',
          fontWeight: 700,
          letterSpacing: '0.1em',
          color: 'var(--text-secondary)'
        }}>Parts</div>
      </div>
      <div className="sidebar-content">
        <button type="button" className="panel-title panel-toggle" onClick={onToggle}>Parts</button>
        {collapsed ? null : (
          <>
            <div className="parts-controls">
              <label className="parts-version-field">
                <span>Version</span>
                <select
                  aria-label="Version filter"
                  value={versionFilter}
                  onChange={(event) => setVersionFilter(event.target.value)}
                >
                  <option value={ACTIVE_FILTER}>{activeVersion ? `Active ${activeVersion}` : 'Active'}</option>
                  <option value={ALL_FILTER}>All</option>
                  {versions.map((version) => (
                    <option key={version} value={version}>{version}</option>
                  ))}
                </select>
              </label>
              <div className="parts-role-toggles" aria-label="Role filters">
                {ROLE_FILTERS.map((filter) => (
                  <button
                    key={filter.role}
                    type="button"
                    className={`part-filter-toggle ${roleVisibility[filter.role] ? 'active' : ''}`}
                    aria-pressed={roleVisibility[filter.role]}
                    onClick={() => toggleRole(filter.role)}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>
              <div className="parts-color-toggles" aria-label="Color mode">
                <button
                  type="button"
                  className={`part-filter-toggle ${colorMode === 'workbench' ? 'active' : ''}`}
                  aria-pressed={colorMode === 'workbench'}
                  onClick={() => onColorModeChange?.('workbench')}
                >
                  Workbench
                </button>
                <button
                  type="button"
                  className={`part-filter-toggle ${colorMode === 'model' ? 'active' : ''}`}
                  aria-pressed={colorMode === 'model'}
                  onClick={() => onColorModeChange?.('model')}
                >
                  Model
                </button>
              </div>
              <div className="parts-detail-controls">
                <button
                  type="button"
                  className="part-detail-control"
                  onClick={openSelectedDetails}
                  disabled={!selectedIds.length}
                >
                  Open selected
                </button>
                <button
                  type="button"
                  className="part-detail-control"
                  onClick={() => setExpandedIds([])}
                  disabled={!expandedIds.length}
                >
                  Close details
                </button>
              </div>
            </div>
            <div className="parts-tree">
              {groups.length ? groups.map((versionGroup) => (
                <section key={versionGroup.version} className="parts-version-group">
                  <div className="parts-version-heading">
                    <span>{versionGroup.version}</span>
                    {versionGroup.version === activeVersion ? <span className="part-badge">active</span> : null}
                  </div>
                  {versionGroup.roles.map((roleGroup) => (
                    <div key={`${versionGroup.version}:${roleGroup.role}`} className="parts-role-group">
                      <div className="parts-role-heading">{roleLabel(roleGroup.role)}</div>
                      {roleGroup.families.map((familyGroup) => (
                        <div key={`${versionGroup.version}:${roleGroup.role}:${familyGroup.family}`} className="parts-family-group">
                          <div className="parts-family-heading">{familyGroup.family}</div>
                          <ul className="parts-list">
                            {familyGroup.parts.map((part) => {
                              const isSelected = selectedIds.includes(part.id)
                              const isActive = part.id === activeId
                              const isExpanded = expandedIds.includes(part.id)
                              const draft = metadataDrafts[part.id] ?? draftFromPart(part)
                              return (
                                <li
                                  key={part.id}
                                  className={`part-row ${isSelected ? 'selected' : ''} ${isActive ? 'active' : ''}`}
                                >
                                  <div
                                    className="part-row-main"
                                    onClick={(event) => onActivate(part.id, event.ctrlKey || event.metaKey)}
                                  >
                                    <button
                                      type="button"
                                      className="part-expand-toggle"
                                      aria-expanded={isExpanded}
                                      aria-label={`${isExpanded ? 'Hide' : 'Show'} details for ${part.id}`}
                                      onClick={(event) => {
                                        event.stopPropagation()
                                        toggleExpanded(part.id)
                                      }}
                                    >
                                      {isExpanded ? '-' : '+'}
                                    </button>
                                    <div className="part-row-copy">
                                      <div className="part-name">{part.id}</div>
                                      <div className="part-meta">
                                        {familyLabel(part)} / {part.artifact_format ?? 'missing'}
                                      </div>
                                    </div>
                                  </div>
                                  {part.capabilities.mesh_only ? <div className="part-warning">Mesh-only approximate</div> : null}
                                  {isExpanded ? (
                                    <PartDetails
                                      part={part}
                                      draft={draft}
                                      onChange={(patch) => onMetadataChange?.(part.id, patch)}
                                      onReset={() => onMetadataReset?.(part.id)}
                                    />
                                  ) : null}
                                </li>
                              )
                            })}
                          </ul>
                        </div>
                      ))}
                    </div>
                  ))}
                </section>
              )) : <div className="parts-empty">No parts match the current filters.</div>}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

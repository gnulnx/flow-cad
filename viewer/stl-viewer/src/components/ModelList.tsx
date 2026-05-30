import { useEffect, useMemo, useState } from 'react'
import type { ViewerPart } from '../types'

interface ModelListProps {
  parts: ViewerPart[]
  selectedIds: string[]
  activeId: string | null
  activeVersion?: string | null
  onActivate: (partId: string, additive: boolean) => void
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

export default function ModelList({
  parts,
  selectedIds,
  activeId,
  activeVersion,
  onActivate,
  collapsed,
  onToggle,
  width,
  isResizing,
}: ModelListProps) {
  const versions = useMemo(() => uniqueVersions(parts, activeVersion), [activeVersion, parts])
  const [versionFilter, setVersionFilter] = useState(ACTIVE_FILTER)
  const [roleVisibility, setRoleVisibility] = useState(DEFAULT_ROLE_VISIBILITY)

  useEffect(() => {
    setVersionFilter(ACTIVE_FILTER)
  }, [activeVersion])

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
                              return (
                                <li
                                  key={part.id}
                                  className={`part-row ${isSelected ? 'selected' : ''} ${isActive ? 'active' : ''}`}
                                  onClick={(event) => onActivate(part.id, event.ctrlKey || event.metaKey)}
                                >
                                  <div className="part-name">{part.id}</div>
                                  <div className="part-meta">
                                    {familyLabel(part)} / {part.artifact_format ?? 'missing'}
                                  </div>
                                  {part.capabilities.mesh_only ? <div className="part-warning">Mesh-only approximate</div> : null}
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

import type { ViewerPart } from '../types'

interface ModelListProps {
  parts: ViewerPart[]
  selectedIds: string[]
  activeId: string | null
  onActivate: (partId: string, additive: boolean) => void
  collapsed: boolean
  onToggle: () => void
  width?: number
  isResizing?: boolean
}

export default function ModelList({ parts, selectedIds, activeId, onActivate, collapsed, onToggle, width, isResizing }: ModelListProps) {
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
          <ul className="parts-list">
            {parts.map((part) => {
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
                    {part.module_id} / {part.artifact_format ?? 'missing'}
                  </div>
                  {part.capabilities.mesh_only ? <div className="part-warning">⚠️ Mesh-only approximate</div> : null}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

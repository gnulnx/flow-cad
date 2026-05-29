import type { ViewerPart } from '../types'

interface ModelListProps {
  parts: ViewerPart[]
  selectedIds: string[]
  activeId: string | null
  onActivate: (partId: string, additive: boolean) => void
  collapsed: boolean
  onToggle: () => void
}

export default function ModelList({ parts, selectedIds, activeId, onActivate, collapsed, onToggle }: ModelListProps) {
  if (parts.length === 0) return null

  return (
    <div className={`parts-panel ${collapsed ? 'panel-collapsed' : ''}`}>
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
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

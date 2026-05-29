import type { SourceContext } from '../types'

interface SourcePanelProps {
  context: SourceContext | null
  activeId: string | null
  collapsed: boolean
  onToggle: () => void
}

export default function SourcePanel({ context, activeId, collapsed, onToggle }: SourcePanelProps) {
  return (
    <div className={`source-panel ${collapsed ? 'panel-collapsed' : ''}`}>
      <button type="button" className="panel-title panel-toggle" onClick={onToggle}>Source</button>
      {collapsed ? null : (
        context ? (
          <>
            <div className="source-file">{context.relative_file_path}</div>
            <pre className="source-code">{context.excerpt}</pre>
          </>
        ) : (
          <div className="source-empty">{activeId ?? 'No part selected'}</div>
        )
      )}
    </div>
  )
}

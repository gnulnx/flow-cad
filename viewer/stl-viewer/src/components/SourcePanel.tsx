import type { SourceContext } from '../types'

interface SourcePanelProps {
  context: SourceContext | null
  activeId: string | null
}

export default function SourcePanel({ context, activeId }: SourcePanelProps) {
  return (
    <div className="source-panel">
      <div className="panel-title">Source</div>
      {context ? (
        <>
          <div className="source-file">{context.relative_file_path}</div>
          <pre className="source-code">{context.excerpt}</pre>
        </>
      ) : (
        <div className="source-empty">{activeId ?? 'No part selected'}</div>
      )}
    </div>
  )
}

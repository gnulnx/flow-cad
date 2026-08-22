import type { WorkbenchPart } from '../../contracts'

interface InspectorDockProps {
  part: WorkbenchPart | null
}

export function InspectorDock({ part }: InspectorDockProps) {
  return (
    <section className="inspector-dock" aria-labelledby="inspector-title">
      <div className="dock-heading dock-heading--compact">
        <div>
          <span className="eyebrow">Active inspection</span>
          <h2 id="inspector-title">Inspector</h2>
        </div>
      </div>
      {part ? (
        <dl className="inspector-facts">
          <div><dt>Part</dt><dd>{part.key}</dd></div>
          <div><dt>Lifecycle</dt><dd>{part.status}</dd></div>
          <div><dt>Artifact</dt><dd>{part.artifactState}</dd></div>
          <div><dt>Authority</dt><dd>{part.qualityLabel}</dd></div>
          <div><dt>UUID</dt><dd><code>{part.uuid}</code></dd></div>
          {part.warnings.map((warning) => (
            <div className="inspector-warning" key={warning}><dt>Warning</dt><dd>{warning}</dd></div>
          ))}
        </dl>
      ) : (
        <p className="empty-copy">Select a part to inspect its lifecycle and artifact authority.</p>
      )}
    </section>
  )
}

import { useEffect, useState } from 'react'
import type { WorkbenchClient, WorkbenchPart } from '../../contracts'

interface InspectorDockProps {
  client: WorkbenchClient
  part: WorkbenchPart | null
  onBuildSubmitted?(jobId: string): void
}

export function InspectorDock({ client, part, onBuildSubmitted }: InspectorDockProps) {
  const [submitting, setSubmitting] = useState(false)
  const [buildError, setBuildError] = useState<string | null>(null)

  useEffect(() => {
    setSubmitting(false)
    setBuildError(null)
  }, [part?.uuid])

  const submitBuild = async () => {
    if (!part || part.status !== 'active' || submitting) return
    setSubmitting(true)
    setBuildError(null)
    try {
      const job = await client.buildPart(part.uuid, crypto.randomUUID())
      onBuildSubmitted?.(job.id)
    } catch (error: unknown) {
      setBuildError(error instanceof Error ? error.message : String(error))
    } finally {
      setSubmitting(false)
    }
  }

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
      {part?.status === 'active' ? (
        <div className="inspector-actions">
          <button type="button" className="tool-button" disabled={submitting} onClick={() => void submitBuild()}>
            {submitting ? 'Submitting build…' : 'Build selected part'}
          </button>
          {buildError ? <span role="alert">{buildError}</span> : null}
        </div>
      ) : null}
    </section>
  )
}

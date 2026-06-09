import type { DraftAcceptanceArtifacts, DraftPreviewModelPayload, PreviewContext, ProposedPreviewOperation } from '../types'

interface CommandPaneBusyState {
  propose: boolean
  apply: boolean
  preview: boolean
  accept: boolean
  discard: boolean
}

interface CommandPaneProps {
  selectedPartId: string | null
  context: PreviewContext | null
  commandText: string
  proposalWarnings: string[]
  proposedOperations: ProposedPreviewOperation[]
  previewModel: DraftPreviewModelPayload | null
  acceptanceArtifacts: DraftAcceptanceArtifacts | null
  busy: CommandPaneBusyState
  hasTransaction: boolean
  onCommandChange: (value: string) => void
  onPropose: () => void
  onApply: () => void
  onPreview: () => void
  onAccept: () => void
  onDiscard: () => void
  onReset: () => void
}

const DRAFT_OPERATION_ENDPOINTS = {
  box: 'box',
  hole: 'holes',
  'louver-patterns': 'louver-patterns',
  thickness: 'thickness',
  unknown: 'box',
}

function operationLabel(op: ProposedPreviewOperation) {
  return `${DRAFT_OPERATION_ENDPOINTS[op.kind]}: ${op.summary}`
}

function formatDimensions(dimensions: { length_mm: number; width_mm: number; height_mm: number } | null | undefined) {
  if (!dimensions) return 'unknown'
  return `${dimensions.length_mm} × ${dimensions.width_mm} × ${dimensions.height_mm} mm`
}

function formatDimensionDelta(
  current: { length_mm: number; width_mm: number; height_mm: number } | null | undefined,
  draft: { length_mm: number; width_mm: number; height_mm: number } | null | undefined,
) {
  if (!current || !draft) return null
  const deltas = [
    draft.length_mm - current.length_mm,
    draft.width_mm - current.width_mm,
    draft.height_mm - current.height_mm,
  ]
  return deltas.map((delta) => `${delta >= 0 ? '+' : ''}${delta}`).join(' × ')
}

export default function CommandPane({
  selectedPartId,
  context,
  commandText,
  proposalWarnings,
  proposedOperations,
  previewModel,
  acceptanceArtifacts,
  busy,
  hasTransaction,
  onCommandChange,
  onPropose,
  onApply,
  onPreview,
  onAccept,
  onDiscard,
  onReset,
}: CommandPaneProps) {
  const canPropose = Boolean(selectedPartId) && !busy.propose
  const canApply = hasTransaction || Boolean(proposedOperations.length)
  const canPreview = hasTransaction && Boolean(previewModel === null)
  const canAccept = Boolean(previewModel)
  const canDiscard = hasTransaction && !busy.discard

  return (
    <section className="command-pane" aria-label="Command pane">
      <div className="command-pane-header">Command</div>
      <div className="command-pane-body">
        <div className="command-pane-row">
          <h2>Selected Part</h2>
          <div>{selectedPartId ?? 'No part selected'}</div>
        </div>

        <div className="command-pane-row">
          <h3>Context</h3>
          {context ? (
            <ul>
              <li><strong>Module:</strong> {context.module_id}</li>
              <li><strong>Family:</strong> {context.family}</li>
              <li><strong>Material:</strong> {context.material}</li>
              <li><strong>Authority:</strong> {context.geometry_authority}</li>
              <li>
                <strong>Dimensions:</strong>
                {' '}
                {formatDimensions(context.source_measurements)}
              </li>
              <li><strong>Assembly:</strong> {context.active_assembly_id ?? 'none'}</li>
              <li><strong>Project frame:</strong> {context.project_frame?.axes.z_positive ?? '+Z'}</li>
              <li><strong>Local origin:</strong> {context.local_frame?.origin_mm.join(', ') ?? '0, 0, 0'} mm</li>
              <li><strong>Mating:</strong> {context.mating_contracts?.relative_path ?? 'none'}</li>
            </ul>
          ) : (
            <p className="command-pane-empty">Select a registered part to load preview context.</p>
          )}
          {context?.warnings.length ? (
            <ul className="command-pane-warnings">
              {context.warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          ) : null}
        </div>

        <label className="command-text-label" htmlFor="preview-command-input">Command</label>
        <textarea
          id="preview-command-input"
          value={commandText}
          onChange={(event) => onCommandChange(event.target.value)}
          className="command-text-input"
          disabled={!selectedPartId}
        />

        <div className="command-pane-controls">
          <button
            type="button"
            className="btn-tool"
            onClick={onPropose}
            disabled={!canPropose}
          >
            {busy.propose ? 'Proposing...' : 'Propose'}
          </button>
          <button
            type="button"
            className="btn-tool"
            onClick={onApply}
            disabled={!canApply || !selectedPartId || busy.apply}
          >
            {busy.apply ? 'Applying...' : 'Apply'}
          </button>
          <button
            type="button"
            className="btn-tool"
            onClick={onPreview}
            disabled={!canPreview || busy.preview}
          >
            {busy.preview ? 'Loading...' : 'Preview'}
          </button>
          <button
            type="button"
            className="btn-tool"
            onClick={onAccept}
            disabled={!canAccept || busy.accept}
          >
            {busy.accept ? 'Accepting...' : 'Accept'}
          </button>
          <button
            type="button"
            className="btn-tool"
            onClick={onDiscard}
            disabled={!canDiscard || busy.discard}
          >
            {busy.discard ? 'Discarding...' : 'Discard'}
          </button>
          <button
            type="button"
            className="btn-tool"
            onClick={onReset}
          >
            Reset
          </button>
        </div>

        <div className="command-pane-section">
          <h3>Proposed Operations</h3>
          {proposedOperations.length ? (
            <ul className="command-pane-list">
              {proposedOperations.map((operation, index) => (
                <li key={`${operation.kind}-${index}`}>{operationLabel(operation)}</li>
              ))}
            </ul>
          ) : null}
          {proposalWarnings.length ? (
            <ul className="command-pane-warnings">
              {proposalWarnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          ) : null}
        </div>

        <div className="command-pane-section">
          <h3>Preview</h3>
          {previewModel ? (
            <div>
              <p><strong>Model:</strong> {previewModel.model_url}</p>
              <p><strong>Geometry:</strong> {previewModel.geometry_authority}</p>
              <p><strong>Draft:</strong> {formatDimensions(previewModel.dimensions)}</p>
              {formatDimensionDelta(context?.source_measurements, previewModel.dimensions) ? (
                <p><strong>Delta:</strong> {formatDimensionDelta(context?.source_measurements, previewModel.dimensions)} mm</p>
              ) : null}
              {previewModel.facts.length ? (
                <ul>
                  {previewModel.facts.map((fact) => <li key={fact}>{fact}</li>)}
                </ul>
              ) : null}
            </div>
          ) : <p className="command-pane-empty">No preview generated yet.</p>}
        </div>

        <div className="command-pane-section">
          <h3>Acceptance</h3>
          {acceptanceArtifacts ? (
            <div>
              <p><strong>Source patch:</strong> {acceptanceArtifacts.source_patch_path}</p>
              <p><strong>Acceptance:</strong> {acceptanceArtifacts.acceptance_manifest_path}</p>
              {acceptanceArtifacts.source_loop_commands?.length ? (
                <ul className="command-pane-list">
                  {acceptanceArtifacts.source_loop_commands.map((command) => <li key={command}>{command}</li>)}
                </ul>
              ) : null}
              {acceptanceArtifacts.source_patch_preview ? (
                <pre className="command-pane-patch">{acceptanceArtifacts.source_patch_preview}</pre>
              ) : null}
            </div>
          ) : <p className="command-pane-empty">No accepted artifacts.</p>}
        </div>
      </div>
    </section>
  )
}

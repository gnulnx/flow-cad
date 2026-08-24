import { useEffect, useRef, type PointerEvent as ReactPointerEvent } from 'react'
import type { ExactFeatureLoadState } from './useExactFeatures'
import { formatMm, isMeasurementStale, type MeasurementResult, type SnapCandidate } from './measurement'

export type MeasurementToolState = ExactFeatureLoadState
  | { status: 'approximate'; targetCount: number }
  | { status: 'mesh-loading' }

interface MeasurementToolButtonProps {
  active: boolean
  state: MeasurementToolState
  onToggle(): void
}

export function MeasurementToolButton({ active, state, onToggle }: MeasurementToolButtonProps) {
  useEffect(() => {
    const keyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'm' || event.repeat || isEditableTarget(event.target)) return
      event.preventDefault()
      onToggle()
    }
    window.addEventListener('keydown', keyDown)
    return () => window.removeEventListener('keydown', keyDown)
  }, [onToggle])

  const status = state.status === 'ready'
    ? `${state.featureSet.features.length} exact targets`
    : state.status === 'approximate' ? `${state.targetCount} bounded approximate mesh targets`
      : state.status === 'mesh-loading' ? 'Preparing approximate mesh targets'
        : state.status === 'extracting' ? 'Extracting exact targets'
          : state.status === 'loading' ? 'Loading exact targets'
            : state.status === 'failed' ? 'Exact targets unavailable'
              : 'Select a visible STEP part'

  return (
    <button
      type="button"
      className="tool-button measurement-tool-button"
      aria-pressed={active}
      aria-label="Measure geometry"
      title={`${status} · Shortcut M`}
      onClick={onToggle}
    >
      <span aria-hidden="true">⌁</span>
      Measure
      <kbd>M</kbd>
    </button>
  )
}

interface MeasurementOverlayProps {
  active: boolean
  state: MeasurementToolState
  hover: SnapCandidate | null
  start: SnapCandidate | null
  measurements: MeasurementResult[]
  currentPartUuid: string | null
  currentArtifactRevision: string | null
  stageRect: DOMRect | null
  onClear(): void
  onDelete(id: string): void
  onToggleHidden(id: string): void
  onTogglePinned(id: string): void
  onMove(id: string, delta: [number, number]): void
}

export function MeasurementOverlay({
  active,
  state,
  hover,
  start,
  measurements,
  currentPartUuid,
  currentArtifactRevision,
  stageRect,
  onClear,
  onDelete,
  onToggleHidden,
  onTogglePinned,
  onMove,
}: MeasurementOverlayProps) {
  if (!active && measurements.length === 0) return null
  const hoverStyle = hover && stageRect ? {
    left: hover.screen.x - stageRect.left + 12,
    top: hover.screen.y - stageRect.top + 12,
  } : undefined

  return (
    <div className="measurement-layer" aria-label="Measurement overlay">
      {active ? (
        <div className="measurement-mode-status" role="status">
          <strong>Measure · {measurementQuality(state, start)}</strong>
          <span>{measurementStatus(state, start)}</span>
        </div>
      ) : null}
      {active && hover && hoverStyle ? (
        <div className={`measurement-hover measurement-hover--${hover.kind}`} style={hoverStyle}>
          <span className="measurement-snap-dot" aria-hidden="true" />
          <strong>{hover.label}</strong>
          <span>{hover.quality === 'Exact' && hover.kind === 'line_edge'
            ? 'Click for exact edge length'
            : start ? 'Click to finish distance' : 'Click to pin start'}</span>
        </div>
      ) : null}
      {measurements.length ? (
        <div className="measurement-labels" aria-label="Saved measurements">
          <div className="measurement-labels__heading">
            <span>{measurements.length} measurement{measurements.length === 1 ? '' : 's'}</span>
            <button type="button" onClick={onClear}>Clear</button>
          </div>
          {measurements.map((measurement) => (
            <MeasurementLabel
              key={measurement.id}
              measurement={measurement}
              stale={isMeasurementStale(measurement, currentPartUuid, currentArtifactRevision)}
              onDelete={() => onDelete(measurement.id)}
              onToggleHidden={() => onToggleHidden(measurement.id)}
              onTogglePinned={() => onTogglePinned(measurement.id)}
              onMove={(delta) => onMove(measurement.id, delta)}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function MeasurementLabel({
  measurement,
  stale,
  onDelete,
  onToggleHidden,
  onTogglePinned,
  onMove,
}: {
  measurement: MeasurementResult
  stale: boolean
  onDelete(): void
  onToggleHidden(): void
  onTogglePinned(): void
  onMove(delta: [number, number]): void
}) {
  const dragRef = useRef<{ pointerId: number; x: number; y: number } | null>(null)
  const beginDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (measurement.pinned) return
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const drag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const active = dragRef.current
    if (!active || active.pointerId !== event.pointerId) return
    onMove([event.clientX - active.x, event.clientY - active.y])
    dragRef.current = { ...active, x: event.clientX, y: event.clientY }
  }
  const endDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return
    dragRef.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }

  return (
    <article
      className={`measurement-label${stale ? ' measurement-label--stale' : ''}${measurement.hidden ? ' measurement-label--hidden' : ''}`}
      style={{ transform: `translate(${measurement.offsetPx[0]}px, ${measurement.offsetPx[1]}px)` }}
      data-artifact-revision={measurement.binding.artifactRevision}
    >
      <header>
        <button
          type="button"
          className="measurement-label__drag"
          aria-label={`Move ${measurement.title}`}
          title={measurement.pinned ? 'Unpin to move' : 'Drag label'}
          onPointerDown={beginDrag}
          onPointerMove={drag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >⋮⋮</button>
        <strong>{measurement.title}</strong>
        <span className={stale
          ? 'quality-tag quality-tag--stale'
          : `quality-tag${measurement.quality === 'Approximate' ? ' quality-tag--approximate' : ''}`}>{stale ? 'Stale' : measurement.quality}</span>
      </header>
      {!measurement.hidden ? (
        <div className="measurement-label__facts">
          <strong>{formatMm(measurement.totalMm)}</strong>
          <span>ΔX {formatMm(measurement.deltaMm[0])}</span>
          <span>ΔY {formatMm(measurement.deltaMm[1])}</span>
          <span>ΔZ {formatMm(measurement.deltaMm[2])}</span>
        </div>
      ) : <span className="measurement-label__hidden-copy">Label hidden</span>}
      <footer>
        <button type="button" aria-pressed={measurement.pinned} onClick={onTogglePinned}>{measurement.pinned ? 'Unpin' : 'Pin'}</button>
        <button type="button" onClick={onToggleHidden}>{measurement.hidden ? 'Show' : 'Hide'}</button>
        <button type="button" onClick={onDelete}>Delete</button>
      </footer>
    </article>
  )
}

function measurementStatus(state: MeasurementToolState, start: SnapCandidate | null): string {
  if (start) return `${start.label} pinned · choose second point`
  if (state.status === 'ready') return 'Hover an exact target · line edges measure in one click'
  if (state.status === 'approximate') return 'Hover a sampled mesh vertex or edge, or click a visible face · two clicks measure'
  if (state.status === 'mesh-loading') return 'Preparing bounded browser mesh targets…'
  if (state.status === 'extracting') return 'Extracting STEP topology in a cancellable job…'
  if (state.status === 'loading') return 'Checking revision-bound exact targets…'
  if (state.status === 'failed') return state.error
  return 'Select a visible STEP-backed part'
}

function measurementQuality(state: MeasurementToolState, start: SnapCandidate | null): 'Exact' | 'Approximate' {
  if (start) return start.quality
  return state.status === 'approximate' || state.status === 'mesh-loading' ? 'Approximate' : 'Exact'
}

function isEditableTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement
    && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
}

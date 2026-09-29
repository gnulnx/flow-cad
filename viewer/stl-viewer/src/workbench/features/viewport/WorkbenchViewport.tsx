import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { applicationApiUrl } from '../../client'
import type { ArtifactState, WorkbenchClient, WorkbenchPart, Point3 } from '../../contracts'
import { AnnotationOverlay } from '../annotation/AnnotationOverlay'
import { saveAnnotationSnapshot } from '../annotation/client'
import { createAnnotationSnapshotInput } from '../annotation/context'
import type { AnnotationMark } from '../annotation/contracts'
import { MeasurementOverlay, MeasurementToolButton, type MeasurementToolState } from '../measurement/MeasurementTool'
import {
  createDistanceMeasurement,
  createEdgeLengthMeasurement,
  findScreenSpaceSnap,
  type ApproximateMeasurementSource,
  type MeasurementProjectionSource,
  type MeasurementResult,
  type SnapCandidate,
  type MeasurementMode,
  type MeasurementPlane,
  type SnapFilter,
} from '../measurement/measurement'
import { DimensionsPanel, type DisplayBounds } from '../measurement/DimensionsPanel'
import { useMeasurementGesture } from '../measurement/useMeasurementGesture'
import { useExactFeatures } from '../measurement/useExactFeatures'
import { transformExactFeature } from './assembly'
import type { RotationMode } from './navigation'
import { useAgentScreenCapture, type LiveCanvasCaptureMetadata, type LiveViewportSource } from './agentScreen'
import { useAssemblyDisplayQueue } from './useAssemblyDisplayQueue'
import { useViewportContextEmitter, type WorkbenchViewportContext } from './viewportContext'

export type { WorkbenchViewportContext } from './viewportContext'

type ModelLoadState = 'empty' | 'loading' | 'partial' | 'ready' | 'failed'
const ModelCanvas = lazy(() => import('./ModelCanvas'))

interface ModelErrorBoundaryProps {
  resetKey: string | null
  onError(message: string): void
  children: ReactNode
}

class ModelErrorBoundary extends Component<ModelErrorBoundaryProps, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error) {
    this.props.onError(error.message || 'Display artifact could not be parsed')
  }

  componentDidUpdate(previous: ModelErrorBoundaryProps) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) this.setState({ failed: false })
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

export interface AssemblyViewportSnapshot {
  partStates: Record<string, ArtifactState>
  visibleOccurrenceIds: string[]
  artifactHashes: Record<string, string>
}

interface WorkbenchViewportProps {
  client: WorkbenchClient
  onSelectPart?(partUuid: string): void
  parts?: WorkbenchPart[]
  part: WorkbenchPart | null
  visiblePartUuids?: readonly string[] | null
  activeAssemblyId?: string | null
  backendRevision: number | null
  threadId?: string | null
  onAssemblyStateChange?(snapshot: AssemblyViewportSnapshot): void
  onMeasurementsChange?(measurements: MeasurementResult[]): void
  onViewportContextChange?(context: WorkbenchViewportContext): void
  onAskAgentAboutMarkup?(marks: AnnotationMark[]): void
  measurementRestore?: { key: string; measurements: MeasurementResult[] } | null
  fitAssemblyRequest?: number
}

export function WorkbenchViewport({ client, onSelectPart, parts = [], part, visiblePartUuids = null, activeAssemblyId = null, backendRevision, threadId = null, onAssemblyStateChange, onMeasurementsChange, onViewportContextChange, onAskAgentAboutMarkup, measurementRestore = null, fitAssemblyRequest = 0 }: WorkbenchViewportProps) {
  const [selectedComponent, setSelectedComponent] = useState<string | null>(null)
  const [rotationMode, setRotationMode] = useState<RotationMode>('turntable')
  const [fitRequest, setFitRequest] = useState(0)
  const [frameSelectedRequest, setFrameSelectedRequest] = useState(0)
  const [rendererReady, setRendererReady] = useState(false)
  const [rendererError, setRendererError] = useState<string | null>(null)
  const [measureMode, setMeasureMode] = useState(false)
  const [measurementMode, setMeasurementMode] = useState<MeasurementMode>('distance')
  const [snapFilter, setSnapFilter] = useState<SnapFilter>('all')
  const [freePlane, setFreePlane] = useState<MeasurementPlane | 'off'>('off')
  const [dimensionsOpen, setDimensionsOpen] = useState(false)
  const [dimensionScope, setDimensionScope] = useState<'selected' | 'visible'>('selected')
  const [displayBounds, setDisplayBounds] = useState<DisplayBounds>({ selected: null, visible: null, selectedPartUuid: null })
  const [measurements, setMeasurements] = useState<MeasurementResult[]>([])
  const [approximateSource, setApproximateSource] = useState<ApproximateMeasurementSource | null>(null)
  const [annotationSnapshot, setAnnotationSnapshot] = useState<{ marks: AnnotationMark[]; hidden: boolean }>({ marks: [], hidden: false })
  const [latestCapture, setLatestCapture] = useState<LiveCanvasCaptureMetadata | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const annotationOverlayRef = useRef<SVGSVGElement>(null)
  const measurementProjectionRef = useRef<MeasurementProjectionSource | null>(null)
  const liveViewportRef = useRef<(() => LiveViewportSource) | null>(null)
  const assembly = useAssemblyDisplayQueue(parts, activeAssemblyId, part?.uuid ?? null, visiblePartUuids)
  const selectedArtifactRevision = part?.authorityHash ?? part?.displayArtifact?.contentHash ?? null
  const modelSetKey = assembly.models.map((model) => model.key).join('|')
  const displayState: ModelLoadState = rendererError
    ? 'failed'
    : assembly.progress.visible === assembly.progress.total && assembly.progress.total > 0
      ? 'ready'
      : assembly.progress.visible > 0
        ? 'partial'
        : assembly.progress.loading > 0 || assembly.progress.queued > 0
          ? 'loading'
          : assembly.progress.failed > 0
            ? 'failed'
            : 'empty'
  const exactFeatures = useExactFeatures(
    client,
    part?.uuid ?? null,
    part?.authorityHash ?? null,
    measureMode && assembly.partStates[part?.uuid ?? ''] === 'visible' && part?.geometryAuthority === 'step',
  )
  const transformedExactFeatures = useMemo(() => exactFeatures.status === 'ready' && assembly.selectedOccurrence
    ? {
        ...exactFeatures,
        featureSet: {
          ...exactFeatures.featureSet,
          features: exactFeatures.featureSet.features.map((feature) => transformExactFeature(feature, assembly.selectedOccurrence!)),
        },
      }
    : exactFeatures, [assembly.selectedOccurrence, exactFeatures])
  const selectedApproximateSource = approximateSource && approximateSource.partUuid === part?.uuid
    && approximateSource.artifactRevision === selectedArtifactRevision
    ? approximateSource
    : null
  const measurementToolState: MeasurementToolState = part?.geometryAuthority === 'mesh'
    ? selectedApproximateSource
      ? { status: 'approximate', targetCount: selectedApproximateSource.features.length }
      : { status: 'mesh-loading' }
    : transformedExactFeatures
  const rendererBecameReady = useCallback(() => setRendererReady(true), [])
  const rendererFailed = useCallback((message: string) => setRendererError(message), [])
  const registerLiveViewport = useCallback((source: (() => LiveViewportSource) | null) => {
    liveViewportRef.current = source
  }, [])
  const registerMeasurementProjection = useCallback((source: MeasurementProjectionSource | null) => {
    measurementProjectionRef.current = source
  }, [])
  const registerApproximateMeasurementSource = useCallback((source: ApproximateMeasurementSource | null) => {
    setApproximateSource((current) => current === source ? current : source)
  }, [])
  const annotationsChanged = useCallback((marks: AnnotationMark[], hidden: boolean) => {
    setAnnotationSnapshot({ marks, hidden })
  }, [])
  const annotationModeChanged = useCallback((active: boolean) => { if (active) setMeasureMode(false) }, [])
  const liveCaptureCompleted = useCallback((metadata: LiveCanvasCaptureMetadata) => setLatestCapture(metadata), [])
  const getLiveViewport = useCallback(() => liveViewportRef.current?.() ?? null, [])
  const getAnnotationOverlay = useCallback(() => annotationOverlayRef.current, [])
  useAgentScreenCapture({
    enabled: rendererReady && !rendererError && assembly.models.length > 0,
    getSource: getLiveViewport,
    part,
    backendRevision,
    getAnnotationOverlay,
    visibleOccurrenceIds: assembly.visibleOccurrenceIds,
    renderedParts: assembly.models.map((model) => model.part),
    onCaptured: liveCaptureCompleted,
  })
  useViewportContextEmitter({
    getLiveViewport,
    measurements,
    annotationMarks: annotationSnapshot.marks,
    annotationsHidden: annotationSnapshot.hidden,
    latestCapture,
    onChange: onViewportContextChange,
  })

  useEffect(() => {
    if (assembly.models.length === 0) {
      setRendererReady(false)
      setDisplayBounds({ selected: null, visible: null, selectedPartUuid: null })
    }
  }, [assembly.models.length])

  useEffect(() => setRendererError(null), [modelSetKey])

  useEffect(() => {
    if (fitAssemblyRequest > 0) setFitRequest((request) => request + 1)
  }, [fitAssemblyRequest])

  useEffect(() => {
    onAssemblyStateChange?.({
      partStates: assembly.partStates,
      visibleOccurrenceIds: assembly.visibleOccurrenceIds,
      artifactHashes: assembly.artifactHashes,
    })
  }, [assembly.artifactHashes, assembly.partStates, assembly.visibleOccurrenceIds, onAssemblyStateChange])

  useEffect(() => {
    onMeasurementsChange?.(measurements)
  }, [measurements, onMeasurementsChange])

  useEffect(() => {
    if (measurementRestore) setMeasurements(measurementRestore.measurements)
  }, [measurementRestore])

  const toggleMeasureMode = useCallback(() => {
    setMeasureMode((active) => !active)
    setDimensionsOpen(false)
  }, [])
  const exitMeasureMode = useCallback(() => setMeasureMode(false), [])
  const snapAtPointer = useCallback((x: number, y: number, start: SnapCandidate | null) => {
    const source = measurementProjectionRef.current
    if (!measureMode || !source) return null
    const projector = source.createProjector()
    const features = transformedExactFeatures.status === 'ready'
      ? transformedExactFeatures.featureSet.features : selectedApproximateSource?.features ?? []
    const snapped = findScreenSpaceSnap({ x, y }, features, projector, 16,
      measurementMode === 'edge_length' ? 'line_edge' : snapFilter)
    if (snapped) return snapped
    if (measurementMode === 'edge_length') return null
    if (freePlane !== 'off') {
      const bounds = displayBounds.selectedPartUuid === part?.uuid ? displayBounds.selected : null
      const anchor = start?.pointMm ?? (bounds ? bounds.min.map((v, i) => (v + bounds.max[i]) / 2) as Point3 : null)
      return anchor ? source.pickPlanePoint?.(x, y, freePlane, anchor) ?? null : null
    }
    return selectedApproximateSource?.pickFreePoint(x, y) ?? null
  }, [measureMode, transformedExactFeatures, selectedApproximateSource, measurementMode, snapFilter, freePlane, displayBounds, part?.uuid])

  const commitMeasurement = useCallback((start: SnapCandidate, end: SnapCandidate, mode: MeasurementMode) => {
    if (!part || !selectedArtifactRevision) return
    const binding = { partUuid: part.uuid, artifactRevision: selectedArtifactRevision }
    const id = `${part.uuid}:measurement:${crypto.randomUUID()}`
    const result = mode === 'edge_length' ? createEdgeLengthMeasurement(id, end, binding)
      : createDistanceMeasurement(id, start, end, binding)
    if (result) setMeasurements((current) => [...current, result])
  }, [part, selectedArtifactRevision])
  const gesture = useMeasurementGesture({
    active: measureMode, mode: measurementMode,
    resetKey: `${part?.uuid}:${selectedArtifactRevision}:${snapFilter}:${freePlane}:${measurementRestore?.key}:${assembly.partStates[part?.uuid ?? '']}:${JSON.stringify(assembly.selectedOccurrence)}`,
    snap: snapAtPointer, commit: commitMeasurement, exit: exitMeasureMode,
  })
  const { start: startTarget, hover: hoverTarget } = gesture

  const updateMeasurement = useCallback((id: string, update: (record: MeasurementResult) => MeasurementResult) => {
    setMeasurements((current) => current.map((record) => record.id === id ? update(record) : record))
  }, [])

  const saveAnnotations = useCallback(async (marks: AnnotationMark[], hidden: boolean) => {
    const source = liveViewportRef.current?.()
    if (!threadId || !part || !selectedArtifactRevision || backendRevision === null || !source) {
      throw new Error('A loaded part and persistent design thread are required to save annotations')
    }
    await saveAnnotationSnapshot(applicationApiUrl(''), createAnnotationSnapshotInput({
      requestId: globalThis.crypto?.randomUUID?.() ?? `annotation-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      threadId,
      marks,
      hidden,
      source,
      part,
      artifactRevision: selectedArtifactRevision,
      visibleOccurrenceIds: assembly.visibleOccurrenceIds,
      backendRevision,
    }))
  }, [assembly.visibleOccurrenceIds, backendRevision, part, selectedArtifactRevision, threadId])

  return (
    <section className="viewport-panel" aria-labelledby="viewport-title">
      <div className="viewport-toolbar">
        <div>
          <span className="eyebrow">Viewport</span>
          <h1 id="viewport-title">{part?.displayName ?? part?.key ?? 'Assembly review'}</h1>
        </div>
        <div className="viewport-actions" aria-label="Viewport controls">
          <div className="segmented-control" aria-label="Rotation mode">
            {([
              ['turntable', 'Turntable'],
              ['arcball', 'Arcball'],
              ['free-orbit', 'Free orbit'],
            ] as const).map(([mode, label]) => (
              <button
                type="button"
                key={mode}
                aria-pressed={rotationMode === mode}
                onClick={() => setRotationMode(mode)}
              >
                {label}
              </button>
            ))}
          </div>
          <button type="button" className="tool-button" onClick={() => setFitRequest((request) => request + 1)}>Fit</button>
          <button type="button" className="tool-button" onClick={() => setFrameSelectedRequest((request) => request + 1)}>Frame part</button>
          <button type="button" className="tool-button" aria-pressed={dimensionsOpen} onClick={() => { setDimensionsOpen((open) => !open); setMeasureMode(false) }}>Dimensions</button>
          <MeasurementToolButton active={measureMode} state={measurementToolState} onToggle={toggleMeasureMode} />
        </div>
      </div>
      <div
        ref={stageRef}
        className={`viewport-stage${measureMode ? ' viewport-stage--measuring' : ''}`}
        onPointerDown={gesture.onPointerDown}
        onPointerMove={gesture.onPointerMove}
        onPointerUp={gesture.onPointerUp}
        onPointerCancel={gesture.onPointerCancel}
        onPointerLeave={gesture.onPointerLeave}
      >
        {assembly.models.length > 0 ? (
          <ModelErrorBoundary resetKey={modelSetKey} onError={rendererFailed}>
            <Suspense fallback={(
              <div className="viewport-state viewport-state--loading" aria-live="polite">
                <div className="viewport-state__glyph" aria-hidden="true"><span /></div>
                <strong>Preparing geometry renderer</strong>
                <span>The workbench shell remains interactive.</span>
              </div>
            )}>
              <ModelCanvas
                models={assembly.models}
                selectedPartUuid={part?.uuid ?? null}
                onSelectPart={onSelectPart}
                onComponentSelected={setSelectedComponent}
                rotationMode={rotationMode}
                assemblyLoading={assembly.progress.loading > 0 || assembly.progress.queued > 0}
                fitRequest={fitRequest}
                frameSelectedRequest={frameSelectedRequest}
                onReady={rendererBecameReady}
                onPartReady={assembly.reportVisible}
                onPartError={assembly.reportParseFailure}
                registerLiveViewport={registerLiveViewport}
                registerMeasurementProjection={registerMeasurementProjection}
                registerApproximateMeasurementSource={registerApproximateMeasurementSource}
                dimensionScope={dimensionsOpen ? dimensionScope : null}
                onBoundsChange={setDisplayBounds}
                measureMode={measureMode}
                measurementHover={hoverTarget}
                measurementStart={startTarget}
                measurements={measurements}
                currentPartUuid={part?.uuid ?? null}
                currentArtifactRevision={selectedArtifactRevision}
              />
            </Suspense>
          </ModelErrorBoundary>
        ) : (
          <div className={`viewport-state viewport-state--${displayState}`} aria-live="polite">
            <div className="viewport-state__glyph" aria-hidden="true"><span /></div>
            {displayState === 'loading' ? (
              <><strong>Loading active assembly</strong><span>Selected geometry first · {assembly.progress.loading} loading · {assembly.progress.queued} queued</span></>
            ) : displayState === 'failed' ? (
              <><strong>Display artifacts failed</strong><span>{assembly.progress.failed} model{assembly.progress.failed === 1 ? '' : 's'} could not be loaded</span></>
            ) : part ? (
              <><strong>No display artifact available</strong><span>{part.artifactState} · {part.qualityLabel}</span></>
            ) : (
              <><strong>Select a part to begin</strong><span>The shell stays interactive while geometry is indexed.</span></>
            )}
          </div>
        )}
        {rendererError ? (
          <div className="viewport-state viewport-state--failed" aria-live="polite">
            <div className="viewport-state__glyph" aria-hidden="true"><span /></div>
            <strong>Display artifact is corrupt or unsupported</strong>
            <span>{rendererError}</span>
          </div>
        ) : null}
        <div className="viewport-progress" data-state={displayState}>
          <span className={`artifact-state artifact-state--${displayState === 'ready' || displayState === 'partial' ? 'visible' : displayState}`} />
          <span>{assemblyProgressLabel(assembly.progress)}</span>
          {assembly.progress.total > 0 ? <progress value={assembly.progress.visible + assembly.progress.failed} max={assembly.progress.total} aria-label="Assembly loading progress" /> : null}
        </div>
        {assembly.models.some((model) => model.displayWarning) ? <div className="display-color-warning" role="status">{assembly.models.find((model) => model.displayWarning)?.displayWarning}</div> : null}
        {selectedComponent ? <div className="component-selection" role="status">Selected: {selectedComponent}</div> : null}
        <div className="navigation-hint">{measureMode ? 'Left select / drag measure · Right / middle pan · Wheel dolly · Esc cancel' : 'Click select · Drag rotate · Right / middle pan · Wheel dolly · Z-up'}</div>
        {dimensionsOpen ? <DimensionsPanel
          bounds={dimensionScope === 'visible' ? displayBounds.visible : displayBounds.selectedPartUuid === part?.uuid ? displayBounds.selected : null}
          scope={dimensionScope} onScope={setDimensionScope}
          loading={dimensionScope === 'visible' ? assembly.progress.visible !== assembly.progress.total : assembly.partStates[part?.uuid ?? ''] !== 'visible'}
        /> : null}
        <MeasurementOverlay
          mode={measurementMode} onMode={setMeasurementMode}
          filter={snapFilter} onFilter={setSnapFilter}
          freePlane={freePlane} onFreePlane={setFreePlane}
          partName={part?.displayName ?? part?.key}
          active={measureMode}
          state={measurementToolState}
          hover={hoverTarget}
          start={startTarget}
          measurements={measurements}
          currentPartUuid={part?.uuid ?? null}
          currentArtifactRevision={selectedArtifactRevision}
          stageRect={stageRef.current?.getBoundingClientRect() ?? null}
          onClear={() => setMeasurements([])}
          onDelete={(id) => setMeasurements((current) => current.filter((record) => record.id !== id))}
          onToggleHidden={(id) => updateMeasurement(id, (record) => ({ ...record, hidden: !record.hidden }))}
          onTogglePinned={(id) => updateMeasurement(id, (record) => ({ ...record, pinned: !record.pinned }))}
          onMove={(id, [dx, dy]) => updateMeasurement(id, (record) => ({
            ...record,
            offsetPx: [record.offsetPx[0] + dx, record.offsetPx[1] + dy],
          }))}
        />
        <AnnotationOverlay
          deactivate={measureMode}
          onActiveChange={annotationModeChanged}
          overlayRef={annotationOverlayRef}
          onChange={annotationsChanged}
          onAskAgent={onAskAgentAboutMarkup}
          onSave={threadId && part && selectedArtifactRevision && backendRevision !== null && assembly.partStates[part.uuid] === 'visible'
            ? saveAnnotations
            : undefined}
        />
      </div>
    </section>
  )
}

function assemblyProgressLabel(progress: { total: number; queued: number; loading: number; visible: number; failed: number }): string {
  if (progress.total === 0) return 'Viewport ready'
  if (progress.visible === progress.total) return `${progress.visible} of ${progress.total} assembly parts visible`
  const activity = [
    progress.loading ? `${progress.loading} loading` : '',
    progress.queued ? `${progress.queued} queued` : '',
    progress.failed ? `${progress.failed} failed` : '',
  ].filter(Boolean).join(' · ')
  return `${progress.visible} of ${progress.total} visible${activity ? ` · ${activity}` : ''}`
}

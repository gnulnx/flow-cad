import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { applicationApiUrl } from '../../client'
import type { ArtifactState, WorkbenchClient, WorkbenchPart } from '../../contracts'
import { AnnotationOverlay } from '../annotation/AnnotationOverlay'
import { saveAnnotationSnapshot } from '../annotation/client'
import { createAnnotationSnapshotInput } from '../annotation/context'
import type { AnnotationMark } from '../annotation/contracts'
import { MeasurementOverlay, MeasurementToolButton } from '../measurement/MeasurementTool'
import {
  createDistanceMeasurement,
  createEdgeLengthMeasurement,
  findScreenSpaceSnap,
  type MeasurementProjectionSource,
  type MeasurementResult,
  type SnapCandidate,
} from '../measurement/measurement'
import { useExactFeatures } from '../measurement/useExactFeatures'
import { transformExactFeature } from './assembly'
import type { RotationMode } from './navigation'
import { useAgentScreenCapture, type LiveViewportSource } from './agentScreen'
import { useAssemblyDisplayQueue } from './useAssemblyDisplayQueue'

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
  parts?: WorkbenchPart[]
  part: WorkbenchPart | null
  activeAssemblyId?: string | null
  backendRevision: number | null
  threadId?: string | null
  onAssemblyStateChange?(snapshot: AssemblyViewportSnapshot): void
  onMeasurementsChange?(measurements: MeasurementResult[]): void
  measurementRestore?: { key: string; measurements: MeasurementResult[] } | null
}

export function WorkbenchViewport({ client, parts = [], part, activeAssemblyId = null, backendRevision, threadId = null, onAssemblyStateChange, onMeasurementsChange, measurementRestore = null }: WorkbenchViewportProps) {
  const [rotationMode, setRotationMode] = useState<RotationMode>('turntable')
  const [fitRequest, setFitRequest] = useState(0)
  const [frameSelectedRequest, setFrameSelectedRequest] = useState(0)
  const [rendererReady, setRendererReady] = useState(false)
  const [rendererError, setRendererError] = useState<string | null>(null)
  const [measureMode, setMeasureMode] = useState(false)
  const [hoverTarget, setHoverTarget] = useState<SnapCandidate | null>(null)
  const [startTarget, setStartTarget] = useState<SnapCandidate | null>(null)
  const [measurements, setMeasurements] = useState<MeasurementResult[]>([])
  const measurementSequence = useRef(0)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const annotationOverlayRef = useRef<SVGSVGElement>(null)
  const measurementProjectionRef = useRef<MeasurementProjectionSource | null>(null)
  const liveViewportRef = useRef<(() => LiveViewportSource) | null>(null)
  const assembly = useAssemblyDisplayQueue(parts, activeAssemblyId, part?.uuid ?? null)
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
    assembly.partStates[part?.uuid ?? ''] === 'visible' && part?.geometryAuthority === 'step',
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
  const rendererBecameReady = useCallback(() => setRendererReady(true), [])
  const rendererFailed = useCallback((message: string) => setRendererError(message), [])
  const registerLiveViewport = useCallback((source: (() => LiveViewportSource) | null) => {
    liveViewportRef.current = source
  }, [])
  const registerMeasurementProjection = useCallback((source: MeasurementProjectionSource | null) => {
    measurementProjectionRef.current = source
  }, [])
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
  })

  useEffect(() => {
    if (assembly.models.length === 0) setRendererReady(false)
  }, [assembly.models.length])

  useEffect(() => setRendererError(null), [modelSetKey])

  useEffect(() => {
    onAssemblyStateChange?.({
      partStates: assembly.partStates,
      visibleOccurrenceIds: assembly.visibleOccurrenceIds,
      artifactHashes: assembly.artifactHashes,
    })
  }, [assembly.artifactHashes, assembly.partStates, assembly.visibleOccurrenceIds, onAssemblyStateChange])

  useEffect(() => {
    setHoverTarget(null)
    setStartTarget(null)
  }, [part?.authorityHash, part?.uuid])

  useEffect(() => {
    onMeasurementsChange?.(measurements)
  }, [measurements, onMeasurementsChange])

  useEffect(() => {
    if (!measurementRestore) return
    setMeasurements(measurementRestore.measurements)
    setHoverTarget(null)
    setStartTarget(null)
  }, [measurementRestore])

  const toggleMeasureMode = useCallback(() => {
    setMeasureMode((active) => {
      if (active) {
        setHoverTarget(null)
        setStartTarget(null)
      }
      return !active
    })
  }, [])

  const snapAtPointer = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!measureMode || transformedExactFeatures.status !== 'ready' || !measurementProjectionRef.current) return null
    return findScreenSpaceSnap(
      { x: event.clientX, y: event.clientY },
      transformedExactFeatures.featureSet.features,
      measurementProjectionRef.current.createProjector(),
    )
  }, [measureMode, transformedExactFeatures])

  const pointerMoved = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if ((event.target as Element).closest?.('.measurement-labels')) return
    setHoverTarget(snapAtPointer(event))
  }, [snapAtPointer])

  const pointerClicked = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!measureMode || event.button !== 0 || (event.target as Element).closest?.('.measurement-labels')) return
    const target = snapAtPointer(event)
    if (!target || !part?.authorityHash) return
    const binding = { partUuid: part.uuid, artifactRevision: part.authorityHash }
    measurementSequence.current += 1
    const id = `${part.uuid}:measurement:${measurementSequence.current}`
    if (target.kind === 'line_edge' && !startTarget) {
      const edge = createEdgeLengthMeasurement(id, target, binding)
      if (edge) setMeasurements((current) => [...current, edge])
      return
    }
    if (!startTarget) {
      setStartTarget(target)
      return
    }
    setMeasurements((current) => [...current, createDistanceMeasurement(id, startTarget, target, binding)])
    setStartTarget(null)
  }, [measureMode, part, snapAtPointer, startTarget])

  const updateMeasurement = useCallback((id: string, update: (record: MeasurementResult) => MeasurementResult) => {
    setMeasurements((current) => current.map((record) => record.id === id ? update(record) : record))
  }, [])

  const selectedArtifactRevision = part?.authorityHash ?? part?.displayArtifact?.contentHash ?? null
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
          <h1 id="viewport-title">{part?.key ?? 'Assembly review'}</h1>
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
          <MeasurementToolButton active={measureMode} state={transformedExactFeatures} onToggle={toggleMeasureMode} />
        </div>
      </div>
      <div
        ref={stageRef}
        className={`viewport-stage${measureMode ? ' viewport-stage--measuring' : ''}`}
        onPointerMove={pointerMoved}
        onPointerLeave={() => setHoverTarget(null)}
        onClick={pointerClicked}
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
                rotationMode={rotationMode}
                fitRequest={fitRequest}
                frameSelectedRequest={frameSelectedRequest}
                onReady={rendererBecameReady}
                onPartReady={assembly.reportVisible}
                onPartError={assembly.reportParseFailure}
                registerLiveViewport={registerLiveViewport}
                registerMeasurementProjection={registerMeasurementProjection}
                measureMode={measureMode}
                measurementHover={hoverTarget}
                measurementStart={startTarget}
                measurements={measurements}
                currentPartUuid={part?.uuid ?? null}
                currentArtifactRevision={part?.authorityHash ?? null}
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
        <div className="navigation-hint">{measureMode ? 'Left select · Right / middle pan · Wheel dolly · Z-up' : 'Left rotate · Right / middle pan · Wheel dolly · Z-up'}</div>
        <MeasurementOverlay
          active={measureMode}
          state={transformedExactFeatures}
          hover={hoverTarget}
          start={startTarget}
          measurements={measurements}
          currentPartUuid={part?.uuid ?? null}
          currentArtifactRevision={part?.authorityHash ?? null}
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
          overlayRef={annotationOverlayRef}
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

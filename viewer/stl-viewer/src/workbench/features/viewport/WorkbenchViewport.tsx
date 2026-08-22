import { Component, lazy, Suspense, useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { applicationApiUrl } from '../../client'
import type { DisplayArtifact, WorkbenchClient, WorkbenchPart } from '../../contracts'
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
import type { RotationMode } from './navigation'
import { useAgentScreenCapture, type LiveViewportSource } from './agentScreen'

type ModelLoadState = 'empty' | 'loading' | 'ready' | 'failed'
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

function useDisplayArtifact(artifact: DisplayArtifact | null) {
  const [artifactBytes, setArtifactBytes] = useState<ArrayBuffer | null>(null)
  const [state, setState] = useState<ModelLoadState>('empty')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    if (!artifact) {
      setArtifactBytes(null)
      setState('empty')
      setError(null)
      return () => controller.abort()
    }

    setArtifactBytes(null)
    setState('loading')
    setError(null)
    fetch(artifact.url, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
      return response.arrayBuffer()
    }).then((buffer) => {
      if (controller.signal.aborted) return
      setArtifactBytes(buffer)
      setState('ready')
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      setState('failed')
      setError(reason instanceof Error ? reason.message : 'Display artifact could not be loaded')
    })

    return () => {
      controller.abort()
    }
  }, [artifact])

  return { artifactBytes, state, error }
}

interface WorkbenchViewportProps {
  client: WorkbenchClient
  part: WorkbenchPart | null
  backendRevision: number | null
  threadId?: string | null
  onVisibilityChange?(partUuid: string, visible: boolean): void
  onMeasurementsChange?(measurements: MeasurementResult[]): void
}

export function WorkbenchViewport({ client, part, backendRevision, threadId = null, onVisibilityChange, onMeasurementsChange }: WorkbenchViewportProps) {
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
  const { artifactBytes, state, error } = useDisplayArtifact(part?.displayArtifact ?? null)
  const displayState: ModelLoadState = rendererError ? 'failed' : state === 'ready' && !rendererReady ? 'loading' : state
  const exactFeatures = useExactFeatures(
    client,
    part?.uuid ?? null,
    part?.authorityHash ?? null,
    displayState === 'ready' && part?.geometryAuthority === 'step',
  )
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
    enabled: rendererReady && !rendererError,
    getSource: getLiveViewport,
    part,
    backendRevision,
    getAnnotationOverlay,
  })

  useEffect(() => {
    setRendererReady(false)
    setRendererError(null)
  }, [part?.displayArtifact?.contentHash])

  useEffect(() => {
    setHoverTarget(null)
    setStartTarget(null)
  }, [part?.authorityHash, part?.uuid])

  useEffect(() => {
    onMeasurementsChange?.(measurements)
  }, [measurements, onMeasurementsChange])

  useEffect(() => {
    if (!part) return
    onVisibilityChange?.(part.uuid, displayState === 'ready')
  }, [displayState, onVisibilityChange, part])

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
    if (!measureMode || exactFeatures.status !== 'ready' || !measurementProjectionRef.current) return null
    return findScreenSpaceSnap(
      { x: event.clientX, y: event.clientY },
      exactFeatures.featureSet.features,
      measurementProjectionRef.current.createProjector(),
    )
  }, [exactFeatures, measureMode])

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
      visibleOccurrenceIds: displayState === 'ready' ? part.occurrenceIds : [],
      backendRevision,
    }))
  }, [backendRevision, displayState, part, selectedArtifactRevision, threadId])

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
          <MeasurementToolButton active={measureMode} state={exactFeatures} onToggle={toggleMeasureMode} />
        </div>
      </div>
      <div
        ref={stageRef}
        className={`viewport-stage${measureMode ? ' viewport-stage--measuring' : ''}`}
        onPointerMove={pointerMoved}
        onPointerLeave={() => setHoverTarget(null)}
        onClick={pointerClicked}
      >
        {artifactBytes ? (
          <ModelErrorBoundary resetKey={part?.displayArtifact?.contentHash ?? null} onError={rendererFailed}>
            <Suspense fallback={(
              <div className="viewport-state viewport-state--loading" aria-live="polite">
                <div className="viewport-state__glyph" aria-hidden="true"><span /></div>
                <strong>Preparing geometry renderer</strong>
                <span>The workbench shell remains interactive.</span>
              </div>
            )}>
              <ModelCanvas
                artifactBytes={artifactBytes}
                rotationMode={rotationMode}
                boundsHint={part?.bounds ?? null}
                fitRequest={fitRequest}
                frameSelectedRequest={frameSelectedRequest}
                onReady={rendererBecameReady}
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
          <div className={`viewport-state viewport-state--${state}`} aria-live="polite">
            <div className="viewport-state__glyph" aria-hidden="true"><span /></div>
            {state === 'loading' ? (
              <><strong>Loading selected display artifact</strong><span>{part?.key} · content-addressed model</span></>
            ) : state === 'failed' ? (
              <><strong>Display artifact failed</strong><span>{error ?? rendererError}</span></>
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
          <span className={`artifact-state artifact-state--${displayState === 'ready' ? 'visible' : displayState}`} />
          <span>{displayState === 'ready' ? 'Display artifact visible' : displayState === 'loading' ? 'Loading model' : displayState === 'failed' ? 'Model failed' : 'Viewport ready'}</span>
        </div>
        <div className="navigation-hint">{measureMode ? 'Left select · Right / middle pan · Wheel dolly · Z-up' : 'Left rotate · Right / middle pan · Wheel dolly · Z-up'}</div>
        <MeasurementOverlay
          active={measureMode}
          state={exactFeatures}
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
          onSave={threadId && part && selectedArtifactRevision && backendRevision !== null && displayState === 'ready'
            ? saveAnnotations
            : undefined}
        />
      </div>
    </section>
  )
}

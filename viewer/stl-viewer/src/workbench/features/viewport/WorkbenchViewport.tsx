import { Component, lazy, Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { DisplayArtifact, WorkbenchPart } from '../../contracts'
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
  part: WorkbenchPart | null
  backendRevision: number | null
  onVisibilityChange?(partUuid: string, visible: boolean): void
}

export function WorkbenchViewport({ part, backendRevision, onVisibilityChange }: WorkbenchViewportProps) {
  const [rotationMode, setRotationMode] = useState<RotationMode>('turntable')
  const [fitRequest, setFitRequest] = useState(0)
  const [frameSelectedRequest, setFrameSelectedRequest] = useState(0)
  const [rendererReady, setRendererReady] = useState(false)
  const [rendererError, setRendererError] = useState<string | null>(null)
  const liveViewportRef = useRef<(() => LiveViewportSource) | null>(null)
  const { artifactBytes, state, error } = useDisplayArtifact(part?.displayArtifact ?? null)
  const displayState: ModelLoadState = rendererError ? 'failed' : state === 'ready' && !rendererReady ? 'loading' : state
  const rendererBecameReady = useCallback(() => setRendererReady(true), [])
  const rendererFailed = useCallback((message: string) => setRendererError(message), [])
  const registerLiveViewport = useCallback((source: (() => LiveViewportSource) | null) => {
    liveViewportRef.current = source
  }, [])
  const getLiveViewport = useCallback(() => liveViewportRef.current?.() ?? null, [])
  useAgentScreenCapture({
    enabled: rendererReady && !rendererError,
    getSource: getLiveViewport,
    part,
    backendRevision,
  })

  useEffect(() => {
    setRendererReady(false)
    setRendererError(null)
  }, [part?.displayArtifact?.contentHash])

  useEffect(() => {
    if (!part) return
    onVisibilityChange?.(part.uuid, displayState === 'ready')
  }, [displayState, onVisibilityChange, part])

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
        </div>
      </div>
      <div className="viewport-stage">
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
        <div className="navigation-hint">Left rotate · Right / middle pan · Wheel dolly · Z-up</div>
      </div>
    </section>
  )
}

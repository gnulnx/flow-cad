import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { Grid, Html } from '@react-three/drei'
import ViewportControls from './ViewportControls'
import {
  formatMm,
  freePointTarget,
  measurementSnapFeaturesForModel,
  resolveEdgeLength,
  resolveMeasurement,
  SNAP_KIND_PRIORITY,
  targetFromFeature,
  type MeasurementTarget,
  type ResolvedMeasurement,
} from '../measurement'
import type { ModelData, RotationMode, SnapFeature, ViewerOccurrence } from '../types'
import * as THREE from 'three'

interface ViewerProps {
  models: ModelData[]
  activeName: string | null
  onActiveNameChange: (name: string | null) => void
  onModelActivate: (name: string, additive: boolean) => void
  fitRequest: number
  frameSelectedRequest: number
  rotationMode: RotationMode
  tapeMode: boolean
  clearMeasurementsRequest: number
  onFitToView?: () => void
  onFrameSelected?: () => void
  onReload?: () => void
  onTapeModeChange?: (enabled: boolean) => void
  onClearMeasurements?: () => void
}

type MeasurementMode = 'off' | 'quick' | 'tape'

interface MeasurementAnnotation extends ResolvedMeasurement {
  id: string
  active: boolean
  temporary: boolean
}

interface DraftMeasurement {
  start: MeasurementTarget
  current: MeasurementTarget
  resolved: ResolvedMeasurement
  startX: number
  startY: number
}

interface SnapCandidate {
  target: MeasurementTarget
  screenDistance: number
  depth: number
  visibilityPoints: THREE.Vector3[]
}

function occurrenceRotation(occurrence: ViewerOccurrence): [number, number, number] {
  return [
    THREE.MathUtils.degToRad(occurrence.rotation[0]),
    THREE.MathUtils.degToRad(occurrence.rotation[1]),
    THREE.MathUtils.degToRad(occurrence.rotation[2]),
  ]
}

function occurrenceMatrix(occurrence: ViewerOccurrence) {
  const position = new THREE.Vector3(...occurrence.location)
  const rotation = occurrenceRotation(occurrence)
  const quaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(rotation[0], rotation[1], rotation[2]))
  return new THREE.Matrix4().compose(position, quaternion, new THREE.Vector3(1, 1, 1))
}

function ModelComponent({
  model,
  isActive,
  measurementActive,
  onClick,
}: {
  model: ModelData
  isActive: boolean
  measurementActive: boolean
  onClick: (name: string, additive: boolean) => void
}) {
  const edgeGeometry = useMemo(() => new THREE.EdgesGeometry(model.geometry, 20), [model.geometry])

  useEffect(() => {
    return () => edgeGeometry.dispose()
  }, [edgeGeometry])

  return (
    <group>
      {model.occurrences.map((occurrence) => (
        <group key={occurrence.name} position={occurrence.location} rotation={occurrenceRotation(occurrence)}>
          <mesh
            userData={{ flowPartId: model.partId, flowOccurrenceName: occurrence.name }}
            geometry={model.geometry}
            onClick={(event) => {
              if (measurementActive) {
                event.stopPropagation()
                return
              }
              if (event.delta > 4) return
              event.stopPropagation()
              onClick(model.partId, event.nativeEvent.ctrlKey || event.nativeEvent.metaKey)
            }}
          >
            <meshStandardMaterial
              color={isActive ? '#94a3b8' : '#8b949e'}
              metalness={0.1}
              roughness={0.7}
              emissive={isActive ? '#22d3ee' : '#000000'}
              emissiveIntensity={isActive ? 0.08 : 0}
            />
          </mesh>
          <lineSegments geometry={edgeGeometry}>
            <lineBasicMaterial color={isActive ? '#22d3ee' : '#475569'} />
          </lineSegments>
        </group>
      ))}
    </group>
  )
}

const TRACKING_COLOR = '#22d3ee'
const LOCK_COLOR = '#10b981'
const MUTED_TARGET_COLOR = '#475569'
const SNAP_VISIBILITY_TOLERANCE_MM = 3
const SILHOUETTE_SCREEN_TOLERANCE_PX = 10

function isLockedTarget(target: MeasurementTarget | null) {
  return Boolean(target && target.kind !== 'face_point' && target.kind !== 'free_point')
}

function MeasurementLine({
  start,
  end,
  color,
  subtle = false,
}: {
  start: THREE.Vector3
  end: THREE.Vector3
  color: string
  subtle?: boolean
}) {
  const geometry = useMemo(() => new THREE.BufferGeometry().setFromPoints([start, end]), [
    start.x,
    start.y,
    start.z,
    end.x,
    end.y,
    end.z,
  ])

  useEffect(() => {
    return () => geometry.dispose()
  }, [geometry])

  return (
    <line geometry={geometry}>
      <lineBasicMaterial
        color={color}
        transparent={subtle}
        opacity={subtle ? 0.3 : 1}
        depthTest={true}
        polygonOffset={true}
        polygonOffsetFactor={-2}
        polygonOffsetUnits={-2}
      />
    </line>
  )
}

function MeasurementPolyline({ points, color, subtle = false }: { points: THREE.Vector3[]; color: string; subtle?: boolean }) {
  const geometry = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points])

  useEffect(() => {
    return () => geometry.dispose()
  }, [geometry])

  return (
    <line geometry={geometry}>
      <lineBasicMaterial
        color={color}
        transparent={subtle}
        opacity={subtle ? 0.3 : 1}
        depthTest={true}
        polygonOffset={true}
        polygonOffsetFactor={-2}
        polygonOffsetUnits={-2}
      />
    </line>
  )
}

function MeasurementMarker({
  point,
  locked,
  subtle,
}: {
  point: THREE.Vector3
  locked?: boolean
  subtle?: boolean
}) {
  const color = subtle ? MUTED_TARGET_COLOR : locked ? LOCK_COLOR : TRACKING_COLOR
  return (
    <mesh position={point}>
      <sphereGeometry args={[subtle ? 0.65 : locked ? 1.9 : 1.55, 16, 16]} />
      <meshBasicMaterial
        color={color}
        transparent={subtle}
        opacity={subtle ? 0.25 : 1}
        wireframe={!locked && !subtle}
        depthTest={true}
        polygonOffset={true}
        polygonOffsetFactor={-4}
        polygonOffsetUnits={-4}
      />
    </mesh>
  )
}

function FeatureHighlight({ target, subtle = false }: { target: MeasurementTarget; subtle?: boolean }) {
  const color = subtle ? MUTED_TARGET_COLOR : isLockedTarget(target) ? LOCK_COLOR : TRACKING_COLOR

  if (target.ringPoints && target.ringPoints.length >= 3) {
    return <MeasurementPolyline points={[...target.ringPoints, target.ringPoints[0]]} color={color} subtle={subtle} />
  }

  if (target.segment) {
    return <MeasurementLine start={target.segment.start} end={target.segment.end} color={color} subtle={subtle} />
  }

  return null
}

function MeasurementLabel({
  annotation,
  onDelete,
}: {
  annotation: MeasurementAnnotation
  onDelete?: (id: string) => void
}) {
  const midpoint = annotation.startPoint.clone().add(annotation.endPoint).multiplyScalar(0.5)

  return (
    <Html position={midpoint} center className="measurement-html">
      <div className={`measurement-label ${annotation.active ? 'measurement-label-active' : ''}`}>
        {onDelete ? (
          <button className="measurement-delete" aria-label="Delete measurement" onClick={() => onDelete(annotation.id)}>
            X
          </button>
        ) : null}
        <div className="measurement-kind">{annotation.label}</div>
        <div className={`measurement-quality measurement-quality-${annotation.qualityLabel.toLowerCase()}`}>
          {annotation.qualityLabel}
        </div>
        <div className="measurement-distance">{formatMm(annotation.distance)}</div>
        <div className="measurement-deltas" aria-label="Measurement deltas">
          <span className="delta-x">DX {formatMm(annotation.delta.x)}</span>
          <span className="delta-y">DY {formatMm(annotation.delta.y)}</span>
          <span className="delta-z">DZ {formatMm(annotation.delta.z)}</span>
        </div>
      </div>
    </Html>
  )
}

function MeasurementAnnotationView({
  annotation,
  onDelete,
  showMarkers = true,
}: {
  annotation: MeasurementAnnotation
  onDelete?: (id: string) => void
  showMarkers?: boolean
}) {
  const color = '#facc15'

  return (
    <group>
      <MeasurementLine start={annotation.startPoint} end={annotation.endPoint} color={color} />
      {showMarkers ? (
        <>
          <MeasurementMarker point={annotation.startPoint} locked={!annotation.label.includes('Free Point')} />
          <MeasurementMarker point={annotation.endPoint} locked={!annotation.label.includes('Free Point')} />
        </>
      ) : null}
      <MeasurementLabel annotation={annotation} onDelete={annotation.temporary ? undefined : onDelete} />
    </group>
  )
}

function MeasurementLayer({
  models,
  mode,
  clearMeasurementsRequest,
}: {
  models: ModelData[]
  mode: MeasurementMode
  clearMeasurementsRequest: number
}) {
  const { camera, gl, scene, raycaster, invalidate } = useThree()
  const [hoverTarget, setHoverTarget] = useState<MeasurementTarget | null>(null)
  const [draft, setDraft] = useState<DraftMeasurement | null>(null)
  const [quickAnnotation, setQuickAnnotation] = useState<MeasurementAnnotation | null>(null)
  const [annotations, setAnnotations] = useState<MeasurementAnnotation[]>([])
  const hoverRef = useRef<MeasurementTarget | null>(null)
  const draftRef = useRef<DraftMeasurement | null>(null)
  const previousTargetRef = useRef<string | null>(null)
  const modeRef = useRef(mode)
  const activeAnnotationRef = useRef<string | null>(null)
  const meshFeatures = useMemo(() => {
    const map = new Map<string, SnapFeature[]>()
    models.forEach((model) => {
      map.set(model.partId, measurementSnapFeaturesForModel(model))
    })
    return map
  }, [models])

  useEffect(() => {
    modeRef.current = mode
    if (mode !== 'quick') {
      setQuickAnnotation(null)
    }
    if (mode === 'off') {
      setHoverTarget(null)
      setDraft(null)
      hoverRef.current = null
      draftRef.current = null
    }
  }, [mode])

  useEffect(() => {
    setAnnotations([])
    setQuickAnnotation(null)
    setDraft(null)
    activeAnnotationRef.current = null
  }, [clearMeasurementsRequest])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Delete' && event.key !== 'Backspace') return
      const activeId = activeAnnotationRef.current
      if (!activeId) return
      setAnnotations((prev) => {
        const next = prev.filter((annotation) => annotation.id !== activeId)
        activeAnnotationRef.current = next.length ? next[next.length - 1].id : null
        return next.map((annotation) => ({ ...annotation, active: annotation.id === activeAnnotationRef.current }))
      })
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    if (mode === 'off') return
    const element = gl.domElement

    const onPointerMove = (event: PointerEvent) => {
      const nextHover = findSnapTarget(event, element, camera, scene, raycaster, models, meshFeatures, previousTargetRef.current)
      previousTargetRef.current = nextHover?.id ?? previousTargetRef.current
      hoverRef.current = nextHover
      setHoverTarget(nextHover)

      const activeDraft = draftRef.current
      if (activeDraft) {
        const current = nextHover ?? freePointForEvent(event, element, camera, activeDraft.start.point)
        const resolved = resolveMeasurement(activeDraft.start, current)
        const nextDraft = { ...activeDraft, current, resolved }
        draftRef.current = nextDraft
        setDraft(nextDraft)
      }
      invalidate()
    }

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return
      const start = hoverRef.current ?? freePointForEvent(event, element, camera, new THREE.Vector3())
      const resolved = resolveMeasurement(start, start)
      const nextDraft = {
        start,
        current: start,
        resolved,
        startX: event.clientX,
        startY: event.clientY,
      }
      draftRef.current = nextDraft
      setDraft(nextDraft)
      element.setPointerCapture(event.pointerId)
      event.preventDefault()
    }

    const onPointerUp = (event: PointerEvent) => {
      if (event.button !== 0) return
      const activeDraft = draftRef.current
      if (!activeDraft) return
      const pointerDelta = Math.hypot(event.clientX - activeDraft.startX, event.clientY - activeDraft.startY)
      const edgeLength = pointerDelta <= 4 && activeDraft.start.segment
        ? resolveEdgeLength(activeDraft.start)
        : null
      const resolved = edgeLength ?? activeDraft.resolved
      const annotation = annotationFromResolved(resolved, modeRef.current === 'quick')

      if (modeRef.current === 'tape') {
        activeAnnotationRef.current = annotation.id
        setAnnotations((prev) => [...prev.map((item) => ({ ...item, active: false })), annotation])
      } else if (modeRef.current === 'quick') {
        setQuickAnnotation(annotation)
      }

      draftRef.current = null
      setDraft(null)
      if (element.hasPointerCapture(event.pointerId)) {
        element.releasePointerCapture(event.pointerId)
      }
      event.preventDefault()
      invalidate()
    }

    element.addEventListener('pointermove', onPointerMove)
    element.addEventListener('pointerdown', onPointerDown)
    element.addEventListener('pointerup', onPointerUp)
    return () => {
      element.removeEventListener('pointermove', onPointerMove)
      element.removeEventListener('pointerdown', onPointerDown)
      element.removeEventListener('pointerup', onPointerUp)
    }
  }, [camera, gl.domElement, invalidate, meshFeatures, mode, models, raycaster, scene])

  const draftPreview = draft ? annotationFromResolved(draft.resolved, true) : null
  const edgeHoverPreview = !draft && hoverTarget?.segment
    ? annotationFromResolved(resolveEdgeLength(hoverTarget) ?? resolveMeasurement(hoverTarget, hoverTarget), true)
    : null

  const deleteAnnotation = (id: string) => {
    setAnnotations((prev) => {
      const next = prev.filter((annotation) => annotation.id !== id)
      activeAnnotationRef.current = next.length ? next[next.length - 1].id : null
      return next.map((annotation) => ({ ...annotation, active: annotation.id === activeAnnotationRef.current }))
    })
  }

  return (
    <group>
      {annotations.map((annotation) => (
        <MeasurementAnnotationView key={annotation.id} annotation={annotation} onDelete={deleteAnnotation} />
      ))}
      {quickAnnotation ? <MeasurementAnnotationView annotation={quickAnnotation} /> : null}
      {draftPreview ? <MeasurementAnnotationView annotation={draftPreview} /> : null}
      {edgeHoverPreview ? <MeasurementAnnotationView annotation={edgeHoverPreview} showMarkers={false} /> : null}
      {mode !== 'off' && hoverTarget ? <FeatureHighlight target={hoverTarget} /> : null}
      {mode !== 'off' && hoverTarget ? <MeasurementMarker point={hoverTarget.point} locked={isLockedTarget(hoverTarget)} /> : null}
    </group>
  )
}

function SceneContent(props: ViewerProps & { measurementMode: MeasurementMode }) {
  const { models, activeName, onModelActivate, fitRequest, frameSelectedRequest, rotationMode, measurementMode, clearMeasurementsRequest } = props
  return (
    <>
      <ambientLight intensity={0.55} />
      <directionalLight position={[80, 120, 80]} intensity={1.1} />
      <directionalLight position={[-80, -60, -70]} intensity={0.35} color="#f4d35e" />
      <hemisphereLight color="#d8f3ff" groundColor="#253040" intensity={0.45} />
      <axesHelper args={[70]} />
      {models.map((model) => (
        <ModelComponent
          key={model.partId}
          model={model}
          isActive={model.partId === activeName}
          measurementActive={measurementMode !== 'off'}
          onClick={onModelActivate}
        />
      ))}
      <MeasurementLayer models={models} mode={measurementMode} clearMeasurementsRequest={clearMeasurementsRequest} />
      <ViewportControls
        models={models}
        activeName={activeName}
        fitRequest={fitRequest}
        frameSelectedRequest={frameSelectedRequest}
        rotationMode={rotationMode}
        measurementActive={measurementMode !== 'off'}
      />
    </>
  )
}

export default function Viewer(props: ViewerProps) {
  const pointerDownRef = useRef<{ x: number; y: number } | null>(null)
  const maxPointerDeltaRef = useRef(0)
  const [quickMeasureActive, setQuickMeasureActive] = useState(false)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null)
  const measurementMode: MeasurementMode = quickMeasureActive ? 'quick' : props.tapeMode ? 'tape' : 'off'

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'm' || isTextEntryTarget(event.target)) return
      setQuickMeasureActive(true)
    }
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'm') return
      setQuickMeasureActive(false)
    }
    const clearQuickMeasure = () => {
      setQuickMeasureActive(false)
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', clearQuickMeasure)
    document.addEventListener('visibilitychange', clearQuickMeasure)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', clearQuickMeasure)
      document.removeEventListener('visibilitychange', clearQuickMeasure)
    }
  }, [])

  return (
    <div
      style={{ width: '100%', height: '100%', minHeight: 0, position: 'relative' }}
      onContextMenu={(event) => {
        if (event.ctrlKey || event.metaKey) {
          event.preventDefault()
          setContextMenu({ x: event.clientX, y: event.clientY })
        }
      }}
    >
      <Canvas
        camera={{ position: [140, 110, 140], fov: 45 }}
        shadows
        style={{ width: '100%', height: '100%' }}
        onPointerDown={(event) => {
          pointerDownRef.current = { x: event.clientX, y: event.clientY }
          maxPointerDeltaRef.current = 0
        }}
        onPointerMove={(event) => {
          if (!pointerDownRef.current) return
          maxPointerDeltaRef.current = Math.max(
            maxPointerDeltaRef.current,
            Math.hypot(event.clientX - pointerDownRef.current.x, event.clientY - pointerDownRef.current.y),
          )
        }}
        onPointerUp={() => {
          pointerDownRef.current = null
        }}
        onPointerMissed={(event) => {
          if (measurementMode !== 'off') return
          if (event.type === 'click' && maxPointerDeltaRef.current <= 4) {
            props.onActiveNameChange(null)
          }
        }}
      >
        <SceneContent {...props} measurementMode={measurementMode} />
      </Canvas>
      {props.models.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-title">No visible parts</div>
        </div>
      ) : null}

      {/* Floating Glassmorphic Context Menu (Command/Control + Right Click) */}
      {contextMenu ? (
        <div
          style={{
            position: 'fixed',
            left: contextMenu.x,
            top: contextMenu.y,
            background: 'rgba(13, 20, 37, 0.95)',
            backdropFilter: 'blur(16px)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '8px',
            padding: '6px 0',
            minWidth: 180,
            boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
            zIndex: 9999,
          }}
          ref={(el) => {
            if (!el) return
            const handleClickOutside = (e: MouseEvent) => {
              if (!el.contains(e.target as Node)) {
                setContextMenu(null)
                document.removeEventListener('click', handleClickOutside)
              }
            }
            setTimeout(() => {
              document.addEventListener('click', handleClickOutside)
            }, 0)
          }}
        >
          <div
            style={{
              padding: '6px 14px',
              fontSize: '10px',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: 'var(--accent)',
              borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
              marginBottom: '4px',
            }}
          >
            Quick Actions
          </div>
          <button
            onClick={() => {
              props.onFitToView?.()
              setContextMenu(null)
            }}
            className="context-menu-item"
          >
            🔎 Fit to View
          </button>
          <button
            onClick={() => {
              props.onFrameSelected?.()
              setContextMenu(null)
            }}
            className="context-menu-item"
            disabled={!props.activeName}
          >
            🎯 Frame Selection
          </button>
          <button
            onClick={() => {
              props.onTapeModeChange?.(!props.tapeMode)
              setContextMenu(null)
            }}
            className="context-menu-item"
          >
            {props.tapeMode ? '❌ Exit Tape Mode' : '📏 Enter Tape Mode'}
          </button>
          <button
            onClick={() => {
              props.onClearMeasurements?.()
              setContextMenu(null)
            }}
            className="context-menu-item"
          >
            🗑️ Clear Measurements
          </button>
          <div style={{ height: '1px', background: 'rgba(255, 255, 255, 0.05)', margin: '4px 0' }} />
          <button
            onClick={() => {
              props.onReload?.()
              setContextMenu(null)
            }}
            className="context-menu-item"
          >
            🔄 Reload Project
          </button>
        </div>
      ) : null}
    </div>
  )
}

function annotationFromResolved(resolved: ResolvedMeasurement, temporary: boolean): MeasurementAnnotation {
  return {
    id: `measurement:${Date.now()}:${Math.random().toString(36).slice(2)}`,
    active: !temporary,
    temporary,
    label: resolved.label,
    startPoint: resolved.startPoint.clone(),
    endPoint: resolved.endPoint.clone(),
    distance: resolved.distance,
    delta: resolved.delta.clone(),
    qualityLabel: resolved.qualityLabel,
  }
}

function isTextEntryTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable
}

function findSnapTarget(
  event: PointerEvent,
  element: HTMLElement,
  camera: THREE.Camera,
  scene: THREE.Scene,
  raycaster: THREE.Raycaster,
  models: ModelData[],
  featuresByModel: Map<string, SnapFeature[]>,
  previousTargetId: string | null,
) {
  const rect = element.getBoundingClientRect()
  const pointer = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -(((event.clientY - rect.top) / rect.height) * 2 - 1),
  )
  raycaster.setFromCamera(pointer, camera)
  const meshes: THREE.Object3D[] = []
  scene.traverse((object) => {
    if (object instanceof THREE.Mesh && object.userData.flowPartId) {
      meshes.push(object)
    }
  })
  const hit = raycaster.intersectObjects(meshes, false)[0]
  if (!hit) return null

  const partId = String(hit.object.userData.flowPartId)
  const occurrenceName = String(hit.object.userData.flowOccurrenceName)
  const model = models.find((candidate) => candidate.partId === partId)
  const occurrence = model?.occurrences.find((candidate) => candidate.name === occurrenceName)
  if (!model || !occurrence) return null

  const matrix = occurrenceMatrix(occurrence)
  const candidates = (featuresByModel.get(partId) ?? [])
    .map((feature) => targetFromFeature(feature, matrix, partId, occurrenceName))
    .filter((target): target is MeasurementTarget => Boolean(target))
    .map((target) => withScreenDistance(target, event, rect, camera))
    .filter((candidate) => candidate.screenDistance <= snapReleaseDistance(candidate.target, previousTargetId))
    .filter((candidate) => isVisibleSnapCandidate(candidate, rect, camera, raycaster, hit.object))

  candidates.push({
    target: {
      id: `${partId}:${occurrenceName}:face:${hit.point.x.toFixed(3)}:${hit.point.y.toFixed(3)}:${hit.point.z.toFixed(3)}`,
      kind: 'face_point',
      label: 'Face Point',
      point: hit.point.clone(),
      partId,
      occurrenceName,
      quality: 'approximate',
      qualityLabel: 'Approximate',
    },
    screenDistance: 22,
    depth: hit.distance,
    visibilityPoints: [hit.point.clone()],
  })

  candidates.sort((a, b) => {
    const aScore = snapScore(a.target, a.screenDistance, previousTargetId)
    const bScore = snapScore(b.target, b.screenDistance, previousTargetId)
    return aScore - bScore || a.depth - b.depth
  })
  return candidates[0]?.target ?? null
}

function withScreenDistance(target: MeasurementTarget, event: PointerEvent, rect: DOMRect, camera: THREE.Camera): SnapCandidate {
  const cameraPosition = cameraPositionForDepth(camera)
  if (target.segment && target.kind === 'line_edge') {
    const start = projectToScreen(target.segment.start, rect, camera)
    const end = projectToScreen(target.segment.end, rect, camera)
    const cursor = new THREE.Vector2(event.clientX, event.clientY)
    const closest = closestPointOnScreenSegment(start, end, cursor)
    const worldPoint = target.segment.start.clone().lerp(target.segment.end, closest.t)
    return {
      target: {
        ...target,
        point: worldPoint,
      },
      screenDistance: closest.point.distanceTo(cursor),
      depth: cameraPosition.distanceTo(worldPoint),
      visibilityPoints: [worldPoint],
    }
  }
  const visibilityPoints = target.kind === 'circle_center' && target.ringPoints?.length
    ? target.ringPoints
    : [target.point]
  return {
    target,
    screenDistance: projectToScreen(target.point, rect, camera).distanceTo(new THREE.Vector2(event.clientX, event.clientY)),
    depth: cameraPosition.distanceTo(target.point),
    visibilityPoints,
  }
}

function isVisibleSnapCandidate(
  candidate: SnapCandidate,
  rect: DOMRect,
  camera: THREE.Camera,
  raycaster: THREE.Raycaster,
  object: THREE.Object3D,
) {
  if (!isLockedTarget(candidate.target)) return true
  return candidate.visibilityPoints.some((point) => isVisibleWorldPoint(point, candidate.screenDistance, rect, camera, raycaster, object))
}

function isVisibleWorldPoint(
  point: THREE.Vector3,
  screenDistance: number,
  rect: DOMRect,
  camera: THREE.Camera,
  raycaster: THREE.Raycaster,
  object: THREE.Object3D,
) {
  const screenPoint = projectToScreen(point, rect, camera)
  raycaster.setFromCamera(screenPointToNdc(screenPoint, rect), camera)
  const firstHit = raycaster.intersectObject(object, false)[0]
  if (!firstHit) {
    return screenDistance <= SILHOUETTE_SCREEN_TOLERANCE_PX
  }
  const targetDistance = raycaster.ray.origin.distanceTo(point)
  return Math.abs(firstHit.distance - targetDistance) <= SNAP_VISIBILITY_TOLERANCE_MM
}

function screenPointToNdc(point: THREE.Vector2, rect: DOMRect) {
  return new THREE.Vector2(
    ((point.x - rect.left) / rect.width) * 2 - 1,
    -(((point.y - rect.top) / rect.height) * 2 - 1),
  )
}

export function snapScore(target: MeasurementTarget, screenDistance: number, previousTargetId: string | null) {
  const priority = SNAP_KIND_PRIORITY[target.kind] ?? 10
  const pullBonus = isLockedTarget(target) ? 30 : 0
  const stickyBonus = target.id === previousTargetId ? 32 : 0
  return priority * 40 + screenDistance - pullBonus - stickyBonus
}

export function snapReleaseDistance(target: MeasurementTarget, previousTargetId: string | null) {
  if (target.id === previousTargetId) return 74
  return isLockedTarget(target) ? 56 : 34
}

function projectToScreen(point: THREE.Vector3, rect: DOMRect, camera: THREE.Camera) {
  const projected = point.clone().project(camera)
  return new THREE.Vector2(
    rect.left + ((projected.x + 1) / 2) * rect.width,
    rect.top + ((-projected.y + 1) / 2) * rect.height,
  )
}

function cameraPositionForDepth(camera: THREE.Camera) {
  return camera.getWorldPosition(new THREE.Vector3())
}

function closestPointOnScreenSegment(start: THREE.Vector2, end: THREE.Vector2, point: THREE.Vector2) {
  const segment = end.clone().sub(start)
  const lengthSq = segment.lengthSq()
  if (lengthSq === 0) return { point: start.clone(), t: 0 }
  const t = THREE.MathUtils.clamp(point.clone().sub(start).dot(segment) / lengthSq, 0, 1)
  return { point: start.clone().addScaledVector(segment, t), t }
}

function freePointForEvent(event: PointerEvent, element: HTMLElement, camera: THREE.Camera, anchor: THREE.Vector3) {
  const rect = element.getBoundingClientRect()
  const pointer = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -(((event.clientY - rect.top) / rect.height) * 2 - 1),
  )
  const raycaster = new THREE.Raycaster()
  raycaster.setFromCamera(pointer, camera)
  const normal = camera.getWorldDirection(new THREE.Vector3())
  const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, anchor)
  const point = new THREE.Vector3()
  return freePointTarget(raycaster.ray.intersectPlane(plane, point) ?? anchor)
}

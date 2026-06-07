import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
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
  type MeasurementResolveMode,
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
  onEditEntityPatch?: (componentId: string, patch: Record<string, unknown>) => Promise<void>
}

type MeasurementMode = 'off' | 'quick' | 'tape'

interface MeasurementAnnotation extends ResolvedMeasurement {
  id: string
  active: boolean
  temporary: boolean
  labelOffset: ScreenOffset
  source?: TapeMeasurementSource
}

interface DraftMeasurement {
  start: MeasurementTarget
  current: MeasurementTarget
  resolved: ResolvedMeasurement
  resolveMode: MeasurementResolveMode
  clickTarget: MeasurementTarget
  sourceStart: MeasurementTarget
  sourceCurrent: MeasurementTarget
  startX: number
  startY: number
}

interface SnapCandidate {
  target: MeasurementTarget
  screenDistance: number
  depth: number
  visibilityPoints: THREE.Vector3[]
}

interface ScreenOffset {
  x: number
  y: number
}

interface LabelDragState {
  pointerId: number
  startClientX: number
  startClientY: number
  startOffset: ScreenOffset
}

interface TapeMeasurementSource {
  start: MeasurementTarget
  end: MeasurementTarget
  resolveMode: MeasurementResolveMode
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
  previewOffset,
  onClick,
}: {
  model: ModelData
  isActive: boolean
  measurementActive: boolean
  previewOffset?: THREE.Vector3
  onClick: (name: string, additive: boolean) => void
}) {
  const edgeGeometry = useMemo(() => new THREE.EdgesGeometry(model.geometry, 20), [model.geometry])

  useEffect(() => {
    return () => edgeGeometry.dispose()
  }, [edgeGeometry])

  return (
    <group>
      {model.occurrences.map((occurrence) => (
        <group
          key={occurrence.name}
          position={[
            occurrence.location[0] + (previewOffset?.x ?? 0),
            occurrence.location[1] + (previewOffset?.y ?? 0),
            occurrence.location[2] + (previewOffset?.z ?? 0),
          ]}
          rotation={occurrenceRotation(occurrence)}
        >
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
              color={model.color}
              metalness={0.1}
              roughness={0.7}
              emissive={isActive ? '#22d3ee' : '#000000'}
              emissiveIntensity={isActive ? 0.08 : 0}
            />
          </mesh>
          <lineSegments geometry={edgeGeometry}>
            <lineBasicMaterial color={isActive ? '#22d3ee' : model.wireframeColor} />
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
const DEFAULT_MEASUREMENT_LABEL_OFFSET = { x: 28, y: -88 }

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
  onOffsetChange,
  onResolveModeChange,
}: {
  annotation: MeasurementAnnotation
  onDelete?: (id: string) => void
  onOffsetChange?: (id: string, offset: ScreenOffset) => void
  onResolveModeChange?: (id: string, mode: MeasurementResolveMode) => void
}) {
  const midpoint = annotation.startPoint.clone().add(annotation.endPoint).multiplyScalar(0.5)
  const dragRef = useRef<LabelDragState | null>(null)
  const [dragging, setDragging] = useState(false)
  const showResolveModeToggle = Boolean(
    onResolveModeChange &&
    annotation.source &&
    measurementResolveModesDiffer(annotation.source.start, annotation.source.end),
  )

  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!onOffsetChange || event.button !== 0) return
    if ((event.target as HTMLElement).closest('button')) return
    dragRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startOffset: annotation.labelOffset,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    setDragging(true)
    onOffsetChange(annotation.id, annotation.labelOffset)
    event.preventDefault()
    event.stopPropagation()
  }

  const dragLabel = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId || !onOffsetChange) return
    onOffsetChange(
      annotation.id,
      measurementLabelOffsetAfterDrag(
        drag.startOffset,
        { x: drag.startClientX, y: drag.startClientY },
        { x: event.clientX, y: event.clientY },
      ),
    )
    event.preventDefault()
    event.stopPropagation()
  }

  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    dragRef.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    setDragging(false)
    event.preventDefault()
    event.stopPropagation()
  }

  const changeResolveMode = (mode: MeasurementResolveMode) => (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.preventDefault()
    event.stopPropagation()
    onResolveModeChange?.(annotation.id, mode)
  }

  const stopButtonPointer = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.stopPropagation()
  }

  return (
    <Html position={midpoint} center className="measurement-html">
      <div
        className={`measurement-label-positioner ${onOffsetChange ? 'measurement-label-positioner-draggable' : ''}`}
        style={{ transform: `translate3d(${annotation.labelOffset.x}px, ${annotation.labelOffset.y}px, 0)` }}
      >
        <div
          className={[
            'measurement-label',
            annotation.active ? 'measurement-label-active' : '',
            onOffsetChange ? 'measurement-label-draggable' : '',
            dragging ? 'measurement-label-dragging' : '',
          ].filter(Boolean).join(' ')}
          aria-label={onOffsetChange ? 'Drag measurement label' : undefined}
          title={onOffsetChange ? 'Drag measurement label' : undefined}
          onPointerDown={startDrag}
          onPointerMove={dragLabel}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          {onDelete ? (
            <button className="measurement-delete" aria-label="Delete measurement" onClick={() => onDelete(annotation.id)}>
              X
            </button>
          ) : null}
          <div className="measurement-kind">{annotation.label}</div>
          <div className={`measurement-quality measurement-quality-${annotation.qualityLabel.toLowerCase()}`}>
            {annotation.qualityLabel}
          </div>
          {showResolveModeToggle && annotation.source ? (
            <div className="measurement-mode-toggle" aria-label="Measurement mode">
              <button
                type="button"
                className={`measurement-mode-option ${annotation.source.resolveMode === 'shortest' ? 'measurement-mode-option-active' : ''}`}
                onPointerDown={stopButtonPointer}
                onClick={changeResolveMode('shortest')}
              >
                Shortest
              </button>
              <button
                type="button"
                className={`measurement-mode-option ${annotation.source.resolveMode === 'picked' ? 'measurement-mode-option-active' : ''}`}
                onPointerDown={stopButtonPointer}
                onClick={changeResolveMode('picked')}
              >
                Picked
              </button>
            </div>
          ) : null}
          <div className="measurement-distance">{formatMm(annotation.distance)}</div>
          <div className="measurement-deltas" aria-label="Measurement deltas">
            <span className="delta-x">DX {formatMm(annotation.delta.x)}</span>
            <span className="delta-y">DY {formatMm(annotation.delta.y)}</span>
            <span className="delta-z">DZ {formatMm(annotation.delta.z)}</span>
          </div>
        </div>
      </div>
    </Html>
  )
}

function MeasurementAnnotationView({
  annotation,
  onDelete,
  onLabelOffsetChange,
  onResolveModeChange,
  showMarkers = true,
}: {
  annotation: MeasurementAnnotation
  onDelete?: (id: string) => void
  onLabelOffsetChange?: (id: string, offset: ScreenOffset) => void
  onResolveModeChange?: (id: string, mode: MeasurementResolveMode) => void
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
      <MeasurementLabel
        annotation={annotation}
        onDelete={annotation.temporary ? undefined : onDelete}
        onOffsetChange={annotation.temporary ? undefined : onLabelOffsetChange}
        onResolveModeChange={annotation.temporary ? undefined : onResolveModeChange}
      />
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
        const sourceCurrent = nextHover ?? freePointForEvent(event, element, camera, activeDraft.start.point)
        const current = pickedTapeTarget(sourceCurrent)
        const resolved = resolveMeasurement(activeDraft.start, current, 'picked')
        const nextDraft = { ...activeDraft, current, sourceCurrent, resolved, resolveMode: 'picked' as const }
        draftRef.current = nextDraft
        setDraft(nextDraft)
      }
      invalidate()
    }

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return
      const clickTarget = hoverRef.current ?? freePointForEvent(event, element, camera, new THREE.Vector3())
      const start = pickedTapeTarget(clickTarget)
      const resolved = resolveMeasurement(start, start, 'picked')
      const nextDraft = {
        start,
        current: start,
        resolved,
        resolveMode: 'picked' as const,
        clickTarget,
        sourceStart: clickTarget,
        sourceCurrent: clickTarget,
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
      const edgeLength = pointerDelta <= 4 && activeDraft.clickTarget.segment
        ? resolveEdgeLength(activeDraft.clickTarget)
        : null
      const resolveMode = defaultTapeResolveMode(activeDraft.sourceStart, activeDraft.sourceCurrent)
      const resolved = edgeLength ?? resolveMeasurement(activeDraft.sourceStart, activeDraft.sourceCurrent, resolveMode)
      const annotation = edgeLength
        ? annotationFromResolved(resolved, modeRef.current === 'quick')
        : annotationFromResolved(resolved, modeRef.current === 'quick', {
            start: activeDraft.sourceStart,
            end: activeDraft.sourceCurrent,
            resolveMode,
          })

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

  const visibleDraft = draft ?? draftRef.current
  const draftPreview = visibleDraft
    ? annotationFromResolved(visibleDraft.resolved, true, {
        start: visibleDraft.start,
        end: visibleDraft.current,
        resolveMode: visibleDraft.resolveMode,
      })
    : null
  const edgeHoverTarget = shouldPreviewEdgeLength(Boolean(visibleDraft), hoverTarget) ? hoverTarget : null
  const edgeHoverPreview = edgeHoverTarget
    ? annotationFromResolved(resolveEdgeLength(edgeHoverTarget) ?? resolveMeasurement(edgeHoverTarget, edgeHoverTarget), true)
    : null

  const deleteAnnotation = (id: string) => {
    setAnnotations((prev) => {
      const next = prev.filter((annotation) => annotation.id !== id)
      activeAnnotationRef.current = next.length ? next[next.length - 1].id : null
      return next.map((annotation) => ({ ...annotation, active: annotation.id === activeAnnotationRef.current }))
    })
  }

  const moveAnnotationLabel = (id: string, labelOffset: ScreenOffset) => {
    activeAnnotationRef.current = id
    setAnnotations((prev) => prev.map((annotation) => (
      annotation.id === id
        ? { ...annotation, active: true, labelOffset }
        : { ...annotation, active: false }
    )))
  }

  const changeAnnotationResolveMode = (id: string, resolveMode: MeasurementResolveMode) => {
    activeAnnotationRef.current = id
    setAnnotations((prev) => prev.map((annotation) => {
      if (annotation.id !== id || !annotation.source) return { ...annotation, active: annotation.id === id }
      return annotationWithResolveMode(annotation, resolveMode)
    }))
  }

  return (
    <group>
      {annotations.map((annotation) => (
        <MeasurementAnnotationView
          key={annotation.id}
          annotation={annotation}
          onDelete={deleteAnnotation}
          onLabelOffsetChange={moveAnnotationLabel}
          onResolveModeChange={changeAnnotationResolveMode}
        />
      ))}
      {quickAnnotation ? <MeasurementAnnotationView annotation={quickAnnotation} /> : null}
      {draftPreview ? <MeasurementAnnotationView annotation={draftPreview} /> : null}
      {edgeHoverPreview ? <MeasurementAnnotationView annotation={edgeHoverPreview} showMarkers={false} /> : null}
      {mode !== 'off' && hoverTarget ? <FeatureHighlight target={hoverTarget} /> : null}
      {mode !== 'off' && hoverTarget ? <MeasurementMarker point={hoverTarget.point} locked={isLockedTarget(hoverTarget)} /> : null}
    </group>
  )
}

interface EditDragState {
  pointerId: number
  startCenter: THREE.Vector3
  startPointerPoint: THREE.Vector3
}

interface EditResizeDragState {
  pointerId: number
  axis: AxisName
  direction: 1 | -1
  startSize: THREE.Vector3
  startPointerPoint: THREE.Vector3
}

export type AxisName = 'x' | 'y' | 'z'

const EDIT_AXIS_VECTORS: Record<AxisName, THREE.Vector3> = {
  x: new THREE.Vector3(1, 0, 0),
  y: new THREE.Vector3(0, 1, 0),
  z: new THREE.Vector3(0, 0, 1),
}

const MIN_EDIT_SIZE_MM = 0.1

function EditMoveHandle({
  model,
  previewOffset,
  onPreviewOffsetChange,
  onCommit,
  onDragActiveChange,
}: {
  model: ModelData
  previewOffset: THREE.Vector3
  onPreviewOffsetChange: (partId: string, offset: THREE.Vector3 | null) => void
  onCommit?: (partId: string, patch: Record<string, unknown>) => Promise<void>
  onDragActiveChange: (active: boolean) => void
}) {
  const { camera, gl, raycaster, invalidate } = useThree()
  const dragRef = useRef<EditDragState | null>(null)
  const center = useMemo(() => model.bounds.center.clone().add(previewOffset), [model.bounds.center, previewOffset])
  const handleRadius = Math.max(2.5, Math.min(7, model.bounds.size.length() * 0.05))

  const startDrag = (event: any) => {
    if (event.button !== 0) return
    const startPointerPoint = worldPointOnCameraPlane(event, gl.domElement, camera, raycaster, center)
    if (!startPointerPoint) return
    dragRef.current = {
      pointerId: event.pointerId,
      startCenter: center.clone(),
      startPointerPoint,
    }
    event.target?.setPointerCapture?.(event.pointerId)
    onDragActiveChange(true)
    event.stopPropagation()
    event.nativeEvent?.preventDefault?.()
    invalidate()
  }

  const moveDrag = (event: any) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const currentPointerPoint = worldPointOnCameraPlane(event, gl.domElement, camera, raycaster, drag.startCenter)
    if (!currentPointerPoint) return
    const nextCenter = editMoveCenterAfterDrag(drag.startCenter, drag.startPointerPoint, currentPointerPoint)
    onPreviewOffsetChange(model.partId, nextCenter.sub(model.bounds.center))
    event.stopPropagation()
    event.nativeEvent?.preventDefault?.()
    invalidate()
  }

  const endDrag = (event: any) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    dragRef.current = null
    const currentPointerPoint = worldPointOnCameraPlane(event, gl.domElement, camera, raycaster, drag.startCenter)
    const nextCenter = currentPointerPoint
      ? editMoveCenterAfterDrag(drag.startCenter, drag.startPointerPoint, currentPointerPoint)
      : drag.startCenter
    event.target?.releasePointerCapture?.(event.pointerId)
    onPreviewOffsetChange(model.partId, null)
    onDragActiveChange(false)
    void onCommit?.(model.partId, { translation_mm: vectorToMmTuple(nextCenter) })
    event.stopPropagation()
    event.nativeEvent?.preventDefault?.()
    invalidate()
  }

  return (
    <group position={center}>
      <mesh
        userData={{ flowEditHandle: 'move', flowPartId: model.partId }}
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <sphereGeometry args={[handleRadius, 24, 16]} />
        <meshBasicMaterial color="#10b981" transparent opacity={0.85} depthTest={false} />
      </mesh>
      <mesh>
        <torusGeometry args={[handleRadius * 1.55, Math.max(0.18, handleRadius * 0.08), 12, 36]} />
        <meshBasicMaterial color="#d9f99d" transparent opacity={0.75} depthTest={false} />
      </mesh>
    </group>
  )
}

function EditResizeHandles({
  model,
  previewSize,
  onPreviewSizeChange,
  onCommit,
  onDragActiveChange,
}: {
  model: ModelData
  previewSize: THREE.Vector3
  onPreviewSizeChange: (partId: string, size: THREE.Vector3 | null) => void
  onCommit?: (partId: string, patch: Record<string, unknown>) => Promise<void>
  onDragActiveChange: (active: boolean) => void
}) {
  const { camera, gl, raycaster, invalidate } = useThree()
  const dragRef = useRef<EditResizeDragState | null>(null)
  const center = model.bounds.center
  const handleRadius = Math.max(1.8, Math.min(5, previewSize.length() * 0.035))

  const startResize = (axis: AxisName, direction: 1 | -1) => (event: any) => {
    if (event.button !== 0) return
    const handlePoint = resizeHandlePosition(center, previewSize, axis, direction)
    const startPointerPoint = worldPointOnCameraPlane(event, gl.domElement, camera, raycaster, handlePoint)
    if (!startPointerPoint) return
    dragRef.current = {
      pointerId: event.pointerId,
      axis,
      direction,
      startSize: previewSize.clone(),
      startPointerPoint,
    }
    event.target?.setPointerCapture?.(event.pointerId)
    onDragActiveChange(true)
    event.stopPropagation()
    event.nativeEvent?.preventDefault?.()
    invalidate()
  }

  const moveResize = (event: any) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const currentPointerPoint = worldPointOnCameraPlane(
      event,
      gl.domElement,
      camera,
      raycaster,
      resizeHandlePosition(center, drag.startSize, drag.axis, drag.direction),
    )
    if (!currentPointerPoint) return
    const nextSize = editResizeSizeAfterDrag(
      drag.startSize,
      drag.axis,
      drag.direction,
      drag.startPointerPoint,
      currentPointerPoint,
    )
    onPreviewSizeChange(model.partId, nextSize)
    event.stopPropagation()
    event.nativeEvent?.preventDefault?.()
    invalidate()
  }

  const endResize = (event: any) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    dragRef.current = null
    const currentPointerPoint = worldPointOnCameraPlane(
      event,
      gl.domElement,
      camera,
      raycaster,
      resizeHandlePosition(center, drag.startSize, drag.axis, drag.direction),
    )
    const nextSize = currentPointerPoint
      ? editResizeSizeAfterDrag(drag.startSize, drag.axis, drag.direction, drag.startPointerPoint, currentPointerPoint)
      : drag.startSize
    event.target?.releasePointerCapture?.(event.pointerId)
    onPreviewSizeChange(model.partId, null)
    onDragActiveChange(false)
    void onCommit?.(model.partId, { size_mm: vectorToMmTuple(nextSize) })
    event.stopPropagation()
    event.nativeEvent?.preventDefault?.()
    invalidate()
  }

  const handles: Array<{ axis: AxisName; direction: 1 | -1; color: string }> = [
    { axis: 'x', direction: 1, color: '#ef4444' },
    { axis: 'x', direction: -1, color: '#ef4444' },
    { axis: 'y', direction: 1, color: '#22c55e' },
    { axis: 'y', direction: -1, color: '#22c55e' },
    { axis: 'z', direction: 1, color: '#3b82f6' },
    { axis: 'z', direction: -1, color: '#3b82f6' },
  ]

  return (
    <group>
      <mesh position={center}>
        <boxGeometry args={[previewSize.x, previewSize.y, previewSize.z]} />
        <meshBasicMaterial color="#d9f99d" wireframe transparent opacity={0.55} depthTest={false} />
      </mesh>
      {handles.map((handle) => (
        <mesh
          key={`${handle.axis}:${handle.direction}`}
          position={resizeHandlePosition(center, previewSize, handle.axis, handle.direction)}
          userData={{ flowEditHandle: 'resize', flowPartId: model.partId, axis: handle.axis, direction: handle.direction }}
          onPointerDown={startResize(handle.axis, handle.direction)}
          onPointerMove={moveResize}
          onPointerUp={endResize}
          onPointerCancel={endResize}
        >
          <boxGeometry args={[handleRadius * 1.6, handleRadius * 1.6, handleRadius * 1.6]} />
          <meshBasicMaterial color={handle.color} transparent opacity={0.82} depthTest={false} />
        </mesh>
      ))}
    </group>
  )
}

function SceneContent(props: ViewerProps & { measurementMode: MeasurementMode }) {
  const {
    models,
    activeName,
    onModelActivate,
    fitRequest,
    frameSelectedRequest,
    rotationMode,
    measurementMode,
    clearMeasurementsRequest,
    onEditEntityPatch,
  } = props
  const [editPreviewOffsets, setEditPreviewOffsets] = useState<Record<string, THREE.Vector3>>({})
  const [editPreviewSizes, setEditPreviewSizes] = useState<Record<string, THREE.Vector3>>({})
  const [editDragActive, setEditDragActive] = useState(false)
  const activeEditableModel = measurementMode === 'off' && activeName?.startsWith('edit:')
    ? models.find((model) => model.partId === activeName && model.capabilities.exact_editing)
    : null
  const setPreviewOffset = (partId: string, offset: THREE.Vector3 | null) => {
    setEditPreviewOffsets((current) => {
      const next = { ...current }
      if (offset) {
        next[partId] = offset.clone()
      } else {
        delete next[partId]
      }
      return next
    })
  }
  const setPreviewSize = (partId: string, size: THREE.Vector3 | null) => {
    setEditPreviewSizes((current) => {
      const next = { ...current }
      if (size) {
        next[partId] = size.clone()
      } else {
        delete next[partId]
      }
      return next
    })
  }

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
          measurementActive={measurementMode !== 'off' || editDragActive}
          previewOffset={editPreviewOffsets[model.partId]}
          onClick={onModelActivate}
        />
      ))}
      {activeEditableModel ? (
        <>
          <EditMoveHandle
            model={activeEditableModel}
            previewOffset={editPreviewOffsets[activeEditableModel.partId] ?? new THREE.Vector3()}
            onPreviewOffsetChange={setPreviewOffset}
            onCommit={onEditEntityPatch}
            onDragActiveChange={setEditDragActive}
          />
          <EditResizeHandles
            model={activeEditableModel}
            previewSize={editPreviewSizes[activeEditableModel.partId] ?? activeEditableModel.bounds.size}
            onPreviewSizeChange={setPreviewSize}
            onCommit={onEditEntityPatch}
            onDragActiveChange={setEditDragActive}
          />
        </>
      ) : null}
      <MeasurementLayer models={models} mode={measurementMode} clearMeasurementsRequest={clearMeasurementsRequest} />
      <ViewportControls
        models={models}
        activeName={activeName}
        fitRequest={fitRequest}
        frameSelectedRequest={frameSelectedRequest}
        rotationMode={rotationMode}
        measurementActive={measurementMode !== 'off' || editDragActive}
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

function annotationFromResolved(
  resolved: ResolvedMeasurement,
  temporary: boolean,
  source?: TapeMeasurementSource,
): MeasurementAnnotation {
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
    labelOffset: DEFAULT_MEASUREMENT_LABEL_OFFSET,
    source: source ? cloneTapeMeasurementSource(source) : undefined,
  }
}

function annotationWithResolveMode(annotation: MeasurementAnnotation, resolveMode: MeasurementResolveMode): MeasurementAnnotation {
  if (!annotation.source) return annotation
  const source = cloneTapeMeasurementSource({ ...annotation.source, resolveMode })
  const resolved = resolveMeasurement(source.start, source.end, resolveMode)
  return {
    ...annotation,
    active: true,
    label: resolved.label,
    startPoint: resolved.startPoint.clone(),
    endPoint: resolved.endPoint.clone(),
    distance: resolved.distance,
    delta: resolved.delta.clone(),
    qualityLabel: resolved.qualityLabel,
    source,
  }
}

export function measurementLabelOffsetAfterDrag(
  startOffset: ScreenOffset,
  startPointer: ScreenOffset,
  currentPointer: ScreenOffset,
) {
  return {
    x: startOffset.x + currentPointer.x - startPointer.x,
    y: startOffset.y + currentPointer.y - startPointer.y,
  }
}

export function shouldPreviewEdgeLength(hasActiveDraft: boolean, hoverTarget: MeasurementTarget | null) {
  return !hasActiveDraft && Boolean(hoverTarget?.segment)
}

export function defaultTapeResolveMode(start: MeasurementTarget, end: MeasurementTarget): MeasurementResolveMode {
  if (start.id === end.id && (start.segment || end.segment)) return 'picked'
  return 'shortest'
}

export function measurementResolveModesDiffer(start: MeasurementTarget, end: MeasurementTarget) {
  const shortest = resolveMeasurement(start, end, 'shortest')
  const picked = resolveMeasurement(start, end, 'picked')
  return (
    !vectorsNear(shortest.startPoint, picked.startPoint) ||
    !vectorsNear(shortest.endPoint, picked.endPoint)
  )
}

export function editMoveCenterAfterDrag(
  startCenter: THREE.Vector3,
  startPointerPoint: THREE.Vector3,
  currentPointerPoint: THREE.Vector3,
) {
  return startCenter.clone().add(currentPointerPoint.clone().sub(startPointerPoint))
}

export function editResizeSizeAfterDrag(
  startSize: THREE.Vector3,
  axis: AxisName,
  direction: 1 | -1,
  startPointerPoint: THREE.Vector3,
  currentPointerPoint: THREE.Vector3,
) {
  const axisVector = EDIT_AXIS_VECTORS[axis]
  const signedDelta = currentPointerPoint.clone().sub(startPointerPoint).dot(axisVector) * direction
  const nextSize = startSize.clone()
  nextSize[axis] = Math.max(MIN_EDIT_SIZE_MM, startSize[axis] + signedDelta * 2)
  return nextSize
}

export function pickedTapeTarget(target: MeasurementTarget): MeasurementTarget {
  if (!target.segment) return target
  return {
    ...target,
    point: target.point.clone(),
    segment: undefined,
    length: undefined,
  }
}

function cloneTapeMeasurementSource(source: TapeMeasurementSource): TapeMeasurementSource {
  return {
    start: cloneMeasurementTarget(source.start),
    end: cloneMeasurementTarget(source.end),
    resolveMode: source.resolveMode,
  }
}

function cloneMeasurementTarget(target: MeasurementTarget): MeasurementTarget {
  return {
    ...target,
    point: target.point.clone(),
    segment: target.segment
      ? {
          start: target.segment.start.clone(),
          end: target.segment.end.clone(),
        }
      : undefined,
    ringPoints: target.ringPoints?.map((point) => point.clone()),
  }
}

function vectorsNear(a: THREE.Vector3, b: THREE.Vector3) {
  return a.distanceToSquared(b) < 1e-8
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
  if (target.id === previousTargetId) return 24
  return isLockedTarget(target) ? 24 : 24
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

function worldPointOnCameraPlane(
  event: { clientX: number; clientY: number },
  element: HTMLElement,
  camera: THREE.Camera,
  raycaster: THREE.Raycaster,
  planePoint: THREE.Vector3,
) {
  const rect = element.getBoundingClientRect()
  raycaster.setFromCamera(screenPointToNdc(new THREE.Vector2(event.clientX, event.clientY), rect), camera)
  const normal = camera.getWorldDirection(new THREE.Vector3())
  const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, planePoint)
  const point = new THREE.Vector3()
  return raycaster.ray.intersectPlane(plane, point)
}

function vectorToMmTuple(vector: THREE.Vector3): [number, number, number] {
  return [
    Number(vector.x.toFixed(4)),
    Number(vector.y.toFixed(4)),
    Number(vector.z.toFixed(4)),
  ]
}

function resizeHandlePosition(center: THREE.Vector3, size: THREE.Vector3, axis: AxisName, direction: 1 | -1) {
  return center.clone().add(EDIT_AXIS_VECTORS[axis].clone().multiplyScalar((size[axis] / 2) * direction))
}

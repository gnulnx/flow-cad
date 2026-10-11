import { Canvas, useThree } from '@react-three/fiber'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { isSelectionClick } from './displayScene'
import { acquireDisplay, type DisplayComponent } from './displayGeometry'
import type { Bounds3 } from '../../contracts'
import { deriveApproximateMeshFeatures } from '../measurement/approximate'
import { MeasurementScene } from '../measurement/MeasurementScene'
import { measurementProjection } from '../measurement/projection'
import { DimensionsScene } from '../measurement/DimensionsScene'
import type { DisplayBounds } from '../measurement/DimensionsPanel'
import { featureLabel, type ApproximateMeasurementSource, type MeasurementProjectionSource, type MeasurementResult, type SnapCandidate } from '../measurement/measurement'
import { mergeBounds, transformBounds } from './assembly'
import { NavigationControls } from './NavigationControls'
import type { LiveViewportSource } from './agentScreen'
import type { RotationMode } from './navigation'
import { groundGridPosition } from './navigation'
import type { LoadedAssemblyPart } from './useAssemblyDisplayQueue'
import type { SceneComponent } from './componentInspection'
import { listenForContextClick, pickContextComponent, type ComponentContextRequest } from './componentContext'

interface ModelCanvasProps {
  models: LoadedAssemblyPart[]
  selectedPartUuid: string | null
  onSelectPart?(partUuid: string): void
  selectedComponentKey: string | null
  hiddenComponentKeys: ReadonlySet<string>
  onComponentSelected(key: string | null): void
  onComponentsChange(components: SceneComponent[]): void
  onComponentContextMenu?(request: ComponentContextRequest): void
  rotationMode: RotationMode
  fitRequest: number
  frameSelectedRequest: number
  assemblyLoading?: boolean
  onReady(): void
  onPartReady(partUuid: string): void
  onPartError(partUuid: string, message: string): void
  registerLiveViewport(source: (() => LiveViewportSource) | null): void
  registerMeasurementProjection(source: MeasurementProjectionSource | null): void
  registerApproximateMeasurementSource(source: ApproximateMeasurementSource | null): void
  dimensionScope?: 'selected' | 'visible' | null
  onBoundsChange?(bounds: DisplayBounds): void
  measureMode: boolean
  measurementHover: SnapCandidate | null
  measurementStart: SnapCandidate | null
  measurements: MeasurementResult[]
  currentPartUuid: string | null
  currentArtifactRevision: string | null
}

function LiveViewportBridge({ register }: { register(source: (() => LiveViewportSource) | null): void }) {
  const { camera, gl } = useThree()
  useEffect(() => {
    const source = () => ({
      canvas: gl.domElement,
      camera: {
        position: camera.position.toArray() as [number, number, number],
        up: camera.up.toArray() as [number, number, number],
        quaternion: camera.quaternion.toArray() as [number, number, number, number],
        fov: camera instanceof THREE.PerspectiveCamera ? camera.fov : null,
      },
    })
    register(source)
    return () => register(null)
  }, [camera, gl.domElement, register])
  return null
}

function MeasurementProjectionBridge({ register }: { register(source: MeasurementProjectionSource | null): void }) {
  const { camera, gl } = useThree()
  useEffect(() => {
    register(measurementProjection(camera, () => gl.domElement.getBoundingClientRect()))
    return () => register(null)
  }, [camera, gl.domElement, register])
  return null
}

function geometryBounds(geometry: THREE.BufferGeometry): Bounds3 {
  if (!geometry.boundingBox) geometry.computeBoundingBox()
  const box = geometry.boundingBox
  if (!box) return { min: [0, 0, 0], max: [0, 0, 0] }
  return {
    min: [box.min.x, box.min.y, box.min.z],
    max: [box.max.x, box.max.y, box.max.z],
  }
}

function ComponentContextBridge({ components, onOpen }: { components: SceneComponent[]; onOpen?(request: ComponentContextRequest): void }) {
  const { camera, scene, gl } = useThree()
  const latest = useRef({ components, onOpen })
  latest.current = { components, onOpen }
  useEffect(() => {
    return listenForContextClick(gl.domElement, (clientX, clientY) => {
      const current = latest.current
      if (!current.onOpen) return
      const keys = new Set(current.components.map((component) => component.key))
      current.onOpen({ key: pickContextComponent(scene, camera, gl.domElement.getBoundingClientRect(), clientX, clientY, keys), clientX, clientY })
    })
  }, [camera, scene, gl.domElement])
  return null
}

export default function ModelCanvas({
  models,
  selectedPartUuid,
  onSelectPart,
  onComponentSelected,
  selectedComponentKey,
  hiddenComponentKeys,
  onComponentsChange,
  onComponentContextMenu,
  rotationMode,
  fitRequest,
  frameSelectedRequest,
  assemblyLoading = false,
  onReady,
  onPartReady,
  onPartError,
  registerLiveViewport,
  registerMeasurementProjection,
  registerApproximateMeasurementSource,
  measureMode,
  dimensionScope = null,
  onBoundsChange,
  measurementHover,
  measurementStart,
  measurements,
  currentPartUuid,
  currentArtifactRevision,
}: ModelCanvasProps) {
  const [geometryByKey, setGeometryByKey] = useState<Record<string, DisplayComponent[]>>({})
  const modelReady = useCallback((key: string, partUuid: string, items: DisplayComponent[]) => {
    setGeometryByKey((current) => current[key] === items ? current : { ...current, [key]: items })
    onPartReady(partUuid)
    onReady()
  }, [onPartReady, onReady])
  const removeModel = useCallback((key: string) => {
    setGeometryByKey((current) => {
      if (!(key in current)) return current
      const next = { ...current }
      delete next[key]
      return next
    })
  }, [])
  const sceneComponents = useMemo(() => models.flatMap((model) => describeComponents(model, geometryByKey[model.key] ?? [])), [geometryByKey, models])
  useEffect(() => { onComponentsChange(sceneComponents) }, [sceneComponents, onComponentsChange])
  const visibleComponents = useMemo(() => sceneComponents.filter((component) => !hiddenComponentKeys.has(component.key)), [sceneComponents, hiddenComponentKeys])
  const visibleBounds = useMemo(() => mergeBounds(visibleComponents.map((component) => component.bounds)), [visibleComponents])
  const selectedBounds = useMemo(() => selectedComponentKey
    ? visibleComponents.find((component) => component.key === selectedComponentKey)?.bounds ?? null
    : mergeBounds(visibleComponents.filter((component) => component.partUuid === selectedPartUuid).map((component) => component.bounds)),
  [visibleComponents, selectedComponentKey, selectedPartUuid])
  useEffect(() => {
    onBoundsChange?.({ selected: selectedBounds, visible: visibleBounds, selectedPartUuid })
  }, [onBoundsChange, selectedBounds, visibleBounds, selectedPartUuid])
  const approximateSelection = useMemo(() => {
    const model = models.find((candidate) => candidate.part.uuid === selectedPartUuid && candidate.part.geometryAuthority === 'mesh')
    const info = model ? geometryByKey[model.key]?.[0] : null
    const occurrence = model?.occurrences.find((item) => visibleComponents.some((component) => component.modelKey === model.key && component.occurrenceId === item.id))
    return model && info && occurrence ? { model: { ...model, occurrences: [occurrence] }, geometry: info.geometry } : null
  }, [geometryByKey, models, selectedPartUuid, visibleComponents])

  return (
    <Canvas
      key="logarithmic-depth"
      camera={{ position: [140, 110, 140], fov: 42, near: 0.1, far: 100000, up: [0, 0, 1] }}
      frameloop="demand"
      dpr={[1, 2]}
      // Keep sub-millimetre CAD layers distinct across whole-assembly zoom levels.
      // The key also recreates existing renderers when this constructor option changes.
      gl={{ preserveDrawingBuffer: true, logarithmicDepthBuffer: true }}
      onPointerMissed={(event) => { if (!measureMode && event.button === 0) onComponentSelected(null) }}
    >
      <color attach="background" args={['#10161d']} />
      <hemisphereLight args={['#d3dde6', '#090c16', 1.62]} position={[0, 0, 1000]} />
      <directionalLight position={[240, -150, 340]} color="#d6e0ea" intensity={.82} />
      <directionalLight position={[120, 80, 210]} color="#6b7f95" intensity={.46} />
      <directionalLight position={[-260, 240, 180]} color="#6db6e8" intensity={.04} />
      <gridHelper args={[1000, 40, '#40505d', '#25313b']} position={groundGridPosition(visibleBounds)} rotation={[Math.PI / 2, 0, 0]} />
      <axesHelper args={[45]} />
      {models.map((model) => (
        <AssemblyModel
          key={model.key}
          model={model}
          selectedKey={selectedComponentKey}
          hiddenKeys={hiddenComponentKeys}
          measureMode={measureMode}
          onSelect={(key) => {
            onSelectPart?.(model.part.uuid)
            onComponentSelected(key)
          }}
          onReady={modelReady}
          onRemoved={removeModel}
          onError={onPartError}
        />
      ))}
      {dimensionScope ? <DimensionsScene bounds={dimensionScope === 'selected' ? selectedBounds : visibleBounds} /> : null}
      <MeasurementScene
        hover={measurementHover}
        start={measurementStart}
        measurements={measurements}
        currentPartUuid={currentPartUuid}
        currentArtifactRevision={currentArtifactRevision}
      />
      <NavigationControls
        rotationMode={rotationMode}
        visibleBounds={visibleBounds}
        selectedBounds={selectedBounds}
        fittingReady={!assemblyLoading}
        fitRequest={fitRequest}
        frameSelectedRequest={frameSelectedRequest}
        measureMode={measureMode}
      />
      <LiveViewportBridge register={registerLiveViewport} />
      <ComponentContextBridge components={visibleComponents} onOpen={measureMode ? undefined : onComponentContextMenu} />
      <MeasurementProjectionBridge register={registerMeasurementProjection} />
      <ApproximateMeasurementBridge selected={approximateSelection} register={registerApproximateMeasurementSource} />
    </Canvas>
  )
}

export function AssemblyModel({
  model, selectedKey, hiddenKeys, measureMode, onSelect, onReady, onRemoved, onError,
}: {
  model: LoadedAssemblyPart
  selectedKey: string | null
  hiddenKeys: ReadonlySet<string>
  measureMode: boolean
  onSelect(key: string): void
  onReady(key: string, partUuid: string, items: DisplayComponent[]): void
  onRemoved(key: string): void
  onError(partUuid: string, message: string): void
}) {
  const [components, setComponents] = useState<DisplayComponent[]>([])
  useEffect(() => {
    let cancelled = false
    let release: (() => void) | undefined
    const cacheKey = JSON.stringify([model.part.displaySceneUrl, model.key,
      model.part.displayArtifact?.contentHash, model.format])
    void acquireDisplay(cacheKey, model.artifactBytes, model.format ?? 'stl').then((lease) => {
      if (cancelled) { lease.release(); return }
      release = lease.release
      const items = lease.items
      const bounds = mergeBounds(items.map((item) => geometryBounds(item.geometry)))
      if (!bounds) throw new Error('Display geometry has no bounds')
      setComponents(items)
      // Only STL uses mesh measurement; GLB bounds need no merged vertex copy.
      onReady(model.key, model.part.uuid, items)
    }).catch((reason) => { if (!cancelled) onError(model.part.uuid, String(reason)) })
    return () => {
      cancelled = true
      release?.()
      onRemoved(model.key)
    }
  }, [model.artifactBytes, model.format, model.key, model.part.uuid, onReady, onRemoved, onError])

  return <group>{model.occurrences.map((occurrence) => (
    <group key={occurrence.id} position={occurrence.translationMm}
      rotation={occurrence.rotationDeg.map(THREE.MathUtils.degToRad) as [number, number, number]}>
      {components.map((component, index) => {
        const key = componentKey(model.key, occurrence.id, component.id, index)
        const hidden = hiddenKeys.has(key)
        const selected = key === selectedKey
        return <mesh key={key} name={key} geometry={component.geometry} visible={!hidden}
          raycast={hidden ? skipRaycast : THREE.Mesh.prototype.raycast}
          onClick={(event) => {
            if (!isSelectionClick(event.delta, event.button, measureMode)) return
            event.stopPropagation()
            if (!hidden) onSelect(key)
          }}>
          <meshStandardMaterial color={component.color} metalness={.08} roughness={.58}
            side={THREE.DoubleSide} transparent={component.opacity < 1} opacity={component.opacity}
            emissive={selected ? '#00aadd' : '#000000'} emissiveIntensity={selected ? .45 : 0} />
          {selected ? <SelectionEdges geometry={component.geometry} /> : null}
        </mesh>
      })}
    </group>
  ))}</group>
}

function skipRaycast() { /* Hidden geometry must not intercept clicks on parts behind it. */ }

export function componentKey(modelKey: string, occurrenceId: string, componentId: string, index: number) {
  return JSON.stringify([modelKey, occurrenceId, componentId, index])
}

export function describeComponents(model: LoadedAssemblyPart, items: DisplayComponent[]): SceneComponent[] {
  const counts = new Map<string, number>()
  const totals = new Map<string, number>()
  const name = model.part.displayName ?? model.part.key.replace(/_/g, ' ')
  const labels = items.map((item) => item.label === 'STL mesh' ? name : item.label.replace(/_/g, ' '))
  labels.forEach((label) => totals.set(label, (totals.get(label) ?? 0) + model.occurrences.length))
  return model.occurrences.flatMap((occurrence, occurrenceIndex) => items.map((item, index) => {
    const label = labels[index]
    const ordinal = (counts.get(label) ?? 0) + 1
    counts.set(label, ordinal)
    return {
      key: componentKey(model.key, occurrence.id, item.id, index), modelKey: model.key,
      partUuid: model.part.uuid, occurrenceId: occurrence.id,
      label: `${label}${totals.get(label)! > 1 ? ` (${ordinal})` : ''}`,
      context: `${name}${model.occurrences.length > 1 ? ` · occurrence ${occurrenceIndex + 1}` : ''}`,
      bounds: transformBounds(geometryBounds(item.geometry), occurrence),
    }
  }))
}

function SelectionEdges({ geometry }: { geometry: THREE.BufferGeometry }) {
  const edges = useMemo(() => new THREE.EdgesGeometry(geometry, 28), [geometry])
  useEffect(() => () => edges.dispose(), [edges])
  return <lineSegments geometry={edges} raycast={() => undefined}>
    <lineBasicMaterial color="#6ee7ff" depthTest polygonOffset polygonOffsetFactor={-1} />
  </lineSegments>
}

function ApproximateMeasurementBridge({
  selected,
  register,
}: {
  selected: { model: LoadedAssemblyPart; geometry: THREE.BufferGeometry } | null
  register(source: ApproximateMeasurementSource | null): void
}) {
  const { camera, gl } = useThree()
  const selectedGeometry = selected?.geometry ?? null
  const occurrence = selected?.model.occurrences[0] ?? null
  const selectedPartUuid = selected?.model.part.uuid ?? null
  const artifactRevision = selected?.model.part.displayArtifact?.contentHash ?? null
  const target = useMemo(() => {
    const position = selectedGeometry?.getAttribute('position')
    if (!selectedGeometry || !occurrence || !position || !selectedPartUuid || !artifactRevision) return null
    const derived = deriveApproximateMeshFeatures(position.array, occurrence)
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(derived.pickPositions, 3))
    geometry.computeBoundingSphere()
    const material = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide })
    const mesh = new THREE.Mesh(geometry, material)
    mesh.position.set(...occurrence.translationMm)
    mesh.rotation.set(...occurrence.rotationDeg.map((value) => THREE.MathUtils.degToRad(value)) as [number, number, number])
    mesh.updateMatrixWorld(true)
    return {
      derived,
      geometry,
      material,
      mesh,
      partUuid: selectedPartUuid,
      artifactRevision,
    }
  }, [artifactRevision, occurrence, selectedGeometry, selectedPartUuid])

  useEffect(() => {
    if (!target) {
      register(null)
      return
    }
    const raycaster = new THREE.Raycaster()
    const ndc = new THREE.Vector2()
    const projected = new THREE.Vector3()
    register({
      partUuid: target.partUuid,
      artifactRevision: target.artifactRevision,
      features: target.derived.features,
      pickFreePoint: (clientX, clientY) => {
        const rect = gl.domElement.getBoundingClientRect()
        if (rect.width <= 0 || rect.height <= 0) return null
        ndc.set(
          ((clientX - rect.left) / rect.width) * 2 - 1,
          1 - ((clientY - rect.top) / rect.height) * 2,
        )
        camera.updateMatrixWorld()
        target.mesh.updateMatrixWorld(true)
        raycaster.setFromCamera(ndc, camera)
        const hit = raycaster.intersectObject(target.mesh, false)[0]
        if (!hit) return null
        projected.copy(hit.point).project(camera)
        const pointMm = hit.point.toArray() as [number, number, number]
        return {
          featureId: `mesh_free:${pointMm.map((value) => value.toFixed(4)).join(':')}`,
          kind: 'free_point',
          quality: 'Approximate',
          label: featureLabel('free_point', 'Approximate'),
          pointMm,
          screen: { x: clientX, y: clientY, depth: projected.z, visible: true },
          distancePx: 0,
        }
      },
    })
    return () => {
      register(null)
      target.geometry.dispose()
      target.material.dispose()
    }
  }, [camera, gl.domElement, register, target])

  return null
}

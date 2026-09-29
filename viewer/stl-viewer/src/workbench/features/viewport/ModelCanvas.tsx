import { Canvas, useThree } from '@react-three/fiber'
import { useCallback, useEffect, useMemo, useState } from 'react'
import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { isSelectionClick } from './displayScene'
import { parseDisplay, type DisplayComponent } from './displayGeometry'
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

interface ModelCanvasProps {
  models: LoadedAssemblyPart[]
  selectedPartUuid: string | null
  onSelectPart?(partUuid: string): void
  onComponentSelected?(label: string | null): void
  rotationMode: RotationMode
  fitRequest: number
  frameSelectedRequest: number
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
  geometry.computeBoundingBox()
  const box = geometry.boundingBox
  if (!box) return { min: [0, 0, 0], max: [0, 0, 0] }
  return {
    min: [box.min.x, box.min.y, box.min.z],
    max: [box.max.x, box.max.y, box.max.z],
  }
}

export default function ModelCanvas({
  models,
  selectedPartUuid,
  onSelectPart,
  onComponentSelected,
  rotationMode,
  fitRequest,
  frameSelectedRequest,
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
  const [componentSelection, setComponentSelection] = useState<{ key: string; label: string; bounds: Bounds3; partUuid: string } | null>(null)
  const clearSelection = useCallback(() => { setComponentSelection(null); onComponentSelected?.(null) }, [onComponentSelected])
  useEffect(() => {
    if (componentSelection && (componentSelection.partUuid !== selectedPartUuid || !models.some((model) => componentSelection.key.startsWith(model.key + ':')))) clearSelection()
  }, [selectedPartUuid, models, componentSelection, clearSelection])
  const [geometryByKey, setGeometryByKey] = useState<Record<string, { bounds: Bounds3; geometry: THREE.BufferGeometry }>>({})
  const modelReady = useCallback((key: string, partUuid: string, bounds: Bounds3, geometry: THREE.BufferGeometry) => {
    setGeometryByKey((current) => current[key]?.geometry === geometry ? current : { ...current, [key]: { bounds, geometry } })
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
  const visibleBounds = useMemo(() => mergeBounds(models.flatMap((model) => {
    const info = geometryByKey[model.key]
    return info ? model.occurrences.map((occurrence) => transformBounds(info.bounds, occurrence)) : []
  })), [geometryByKey, models])
  const selectedBounds = useMemo(() => mergeBounds(models
    .filter((model) => model.part.uuid === selectedPartUuid)
    .flatMap((model) => {
      const info = geometryByKey[model.key]
      return info ? model.occurrences.map((occurrence) => transformBounds(info.bounds, occurrence)) : []
    })), [geometryByKey, models, selectedPartUuid])
  useEffect(() => {
    onBoundsChange?.({ selected: selectedBounds, visible: visibleBounds, selectedPartUuid })
  }, [onBoundsChange, selectedBounds, visibleBounds, selectedPartUuid])
  const approximateSelection = useMemo(() => {
    const model = models.find((candidate) => candidate.part.uuid === selectedPartUuid && candidate.part.geometryAuthority === 'mesh')
    const info = model ? geometryByKey[model.key] : null
    return model && info ? { model, geometry: info.geometry } : null
  }, [geometryByKey, models, selectedPartUuid])

  return (
    <Canvas
      camera={{ position: [140, 110, 140], fov: 42, near: 0.1, far: 100000, up: [0, 0, 1] }}
      frameloop="demand"
      dpr={[1, 2]}
      gl={{ preserveDrawingBuffer: true }}
      onPointerMissed={() => { if (!measureMode) clearSelection() }}
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
          selectedKey={componentSelection?.key ?? null}
          measureMode={measureMode}
          onSelect={(key, label, bounds) => {
            onSelectPart?.(model.part.uuid)
            setComponentSelection({ key, label, bounds, partUuid: model.part.uuid })
            onComponentSelected?.(label)
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
        selectedBounds={componentSelection?.bounds ?? selectedBounds}
        fitRequest={fitRequest}
        frameSelectedRequest={frameSelectedRequest}
        measureMode={measureMode}
      />
      <LiveViewportBridge register={registerLiveViewport} />
      <MeasurementProjectionBridge register={registerMeasurementProjection} />
      <ApproximateMeasurementBridge selected={approximateSelection} register={registerApproximateMeasurementSource} />
    </Canvas>
  )
}

function AssemblyModel({
  model, selectedKey, measureMode, onSelect, onReady, onRemoved, onError,
}: {
  model: LoadedAssemblyPart
  selectedKey: string | null
  measureMode: boolean
  onSelect(key: string, label: string, bounds: Bounds3): void
  onReady(key: string, partUuid: string, bounds: Bounds3, geometry: THREE.BufferGeometry): void
  onRemoved(key: string): void
  onError(partUuid: string, message: string): void
}) {
  const [components, setComponents] = useState<DisplayComponent[]>([])
  useEffect(() => {
    let cancelled = false
    let loaded: DisplayComponent[] = []
    let merged: THREE.BufferGeometry | null = null
    void parseDisplay(model.artifactBytes, model.format ?? 'stl').then((items) => {
      if (cancelled) { items.forEach((item) => item.geometry.dispose()); return }
      loaded = items
      // Measurement fallback uses STL only. A merged position-only geometry
      // provides bounds without retaining an extra copy of every normal/index.
      const positions = items.map((item) => {
        const geometry = new THREE.BufferGeometry()
        geometry.setAttribute('position', item.geometry.getAttribute('position'))
        return geometry
      })
      merged = mergeGeometries(positions)
      if (!merged) throw new Error('Display geometry has no bounds')
      positions.forEach((geometry) => geometry.dispose())
      setComponents(items)
      const measureGeometry = (model.format ?? 'stl') === 'stl' ? items[0].geometry : merged
      onReady(model.key, model.part.uuid, geometryBounds(merged), measureGeometry)
    }).catch((reason) => { if (!cancelled) onError(model.part.uuid, String(reason)) })
    return () => {
      cancelled = true
      loaded.forEach((item) => item.geometry.dispose())
      merged?.dispose()
      onRemoved(model.key)
    }
  }, [model.artifactBytes, model.format, model.key, model.part.uuid, onReady, onRemoved, onError])

  return <group>{model.occurrences.map((occurrence) => (
    <group key={occurrence.id} position={occurrence.translationMm}
      rotation={occurrence.rotationDeg.map(THREE.MathUtils.degToRad) as [number, number, number]}>
      {components.map((component) => {
        const key = `${model.key}:${occurrence.id}:${component.id}`
        const selected = key === selectedKey
        return <mesh key={component.id} geometry={component.geometry}
          onClick={(event) => {
            if (!isSelectionClick(event.delta, event.button, measureMode)) return
            event.stopPropagation()
            onSelect(key, component.label.replace(/_/g, ' '), transformBounds(geometryBounds(component.geometry), occurrence))
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

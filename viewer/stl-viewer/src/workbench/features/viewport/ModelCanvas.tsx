import { Canvas, useThree } from '@react-three/fiber'
import { useCallback, useEffect, useMemo, useState } from 'react'
import * as THREE from 'three'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import type { Bounds3 } from '../../contracts'
import { deriveApproximateMeshFeatures } from '../measurement/approximate'
import { MeasurementScene } from '../measurement/MeasurementScene'
import { featureLabel, type ApproximateMeasurementSource, type MeasurementProjectionSource, type MeasurementResult, type SnapCandidate } from '../measurement/measurement'
import { mergeBounds, transformBounds } from './assembly'
import { NavigationControls } from './NavigationControls'
import type { LiveViewportSource } from './agentScreen'
import type { RotationMode } from './navigation'
import type { LoadedAssemblyPart } from './useAssemblyDisplayQueue'

interface ModelCanvasProps {
  models: LoadedAssemblyPart[]
  selectedPartUuid: string | null
  rotationMode: RotationMode
  fitRequest: number
  frameSelectedRequest: number
  onReady(): void
  onPartReady(partUuid: string): void
  onPartError(partUuid: string, message: string): void
  registerLiveViewport(source: (() => LiveViewportSource) | null): void
  registerMeasurementProjection(source: MeasurementProjectionSource | null): void
  registerApproximateMeasurementSource(source: ApproximateMeasurementSource | null): void
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
    register({
      createProjector: () => {
        camera.updateMatrixWorld()
        const rect = gl.domElement.getBoundingClientRect()
        const projected = new THREE.Vector3()
        return (pointMm) => {
          projected.set(...pointMm).project(camera)
          return {
            x: rect.left + (projected.x + 1) * rect.width / 2,
            y: rect.top + (1 - projected.y) * rect.height / 2,
            depth: projected.z,
            visible: projected.z >= -1 && projected.z <= 1,
          }
        }
      },
    })
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
  measurementHover,
  measurementStart,
  measurements,
  currentPartUuid,
  currentArtifactRevision,
}: ModelCanvasProps) {
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
    >
      <color attach="background" args={['#10161d']} />
      <ambientLight intensity={1.35} />
      <directionalLight position={[120, -80, 180]} intensity={2.5} />
      <directionalLight position={[-80, 100, 50]} intensity={1.1} />
      <gridHelper args={[1000, 40, '#40505d', '#25313b']} rotation={[Math.PI / 2, 0, 0]} />
      <axesHelper args={[45]} />
      {models.map((model) => (
        <AssemblyModel
          key={model.key}
          model={model}
          selected={model.part.uuid === selectedPartUuid}
          onReady={modelReady}
          onRemoved={removeModel}
          onError={onPartError}
        />
      ))}
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
  model,
  selected,
  onReady,
  onRemoved,
  onError,
}: {
  model: LoadedAssemblyPart
  selected: boolean
  onReady(key: string, partUuid: string, bounds: Bounds3, geometry: THREE.BufferGeometry): void
  onRemoved(key: string): void
  onError(partUuid: string, message: string): void
}) {
  const parsed = useMemo(() => {
    try {
      const geometry = new STLLoader().parse(model.artifactBytes)
      geometry.computeVertexNormals()
      return { geometry, bounds: geometryBounds(geometry), error: null }
    } catch (reason) {
      return {
        geometry: null,
        bounds: null,
        error: reason instanceof Error ? reason.message : 'Display artifact could not be parsed',
      }
    }
  }, [model.artifactBytes])

  useEffect(() => {
    if (parsed.geometry && parsed.bounds) onReady(model.key, model.part.uuid, parsed.bounds, parsed.geometry)
    else if (parsed.error) onError(model.part.uuid, parsed.error)
    return () => {
      parsed.geometry?.dispose()
      onRemoved(model.key)
    }
  }, [model.key, model.part.uuid, onError, onReady, onRemoved, parsed])

  if (!parsed.geometry) return null
  return (
    <group>
      {model.occurrences.map((occurrence) => (
        <mesh
          key={`${model.key}:${occurrence.id}`}
          geometry={parsed.geometry!}
          position={occurrence.translationMm}
          rotation={occurrence.rotationDeg.map((value) => THREE.MathUtils.degToRad(value)) as [number, number, number]}
          castShadow
          receiveShadow
        >
          <meshStandardMaterial
            color={selected ? '#d8a861' : '#7792a3'}
            metalness={0.08}
            roughness={0.58}
            transparent={model.part.role === 'reference'}
            opacity={model.part.role === 'reference' ? 0.52 : 1}
          />
        </mesh>
      ))}
    </group>
  )
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

import { Canvas, useThree } from '@react-three/fiber'
import { useCallback, useEffect, useMemo, useState } from 'react'
import * as THREE from 'three'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import type { Bounds3 } from '../../contracts'
import { MeasurementScene } from '../measurement/MeasurementScene'
import type { MeasurementProjectionSource, MeasurementResult, SnapCandidate } from '../measurement/measurement'
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
  measureMode,
  measurementHover,
  measurementStart,
  measurements,
  currentPartUuid,
  currentArtifactRevision,
}: ModelCanvasProps) {
  const [boundsByKey, setBoundsByKey] = useState<Record<string, Bounds3>>({})
  const modelReady = useCallback((key: string, partUuid: string, bounds: Bounds3) => {
    setBoundsByKey((current) => current[key] === bounds ? current : { ...current, [key]: bounds })
    onPartReady(partUuid)
    onReady()
  }, [onPartReady, onReady])
  const removeModel = useCallback((key: string) => {
    setBoundsByKey((current) => {
      if (!(key in current)) return current
      const next = { ...current }
      delete next[key]
      return next
    })
  }, [])
  const visibleBounds = useMemo(() => mergeBounds(models.flatMap((model) => {
    const bounds = boundsByKey[model.key]
    return bounds ? model.occurrences.map((occurrence) => transformBounds(bounds, occurrence)) : []
  })), [boundsByKey, models])
  const selectedBounds = useMemo(() => mergeBounds(models
    .filter((model) => model.part.uuid === selectedPartUuid)
    .flatMap((model) => {
      const bounds = boundsByKey[model.key]
      return bounds ? model.occurrences.map((occurrence) => transformBounds(bounds, occurrence)) : []
    })), [boundsByKey, models, selectedPartUuid])

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
  onReady(key: string, partUuid: string, bounds: Bounds3): void
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
    if (parsed.geometry && parsed.bounds) onReady(model.key, model.part.uuid, parsed.bounds)
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

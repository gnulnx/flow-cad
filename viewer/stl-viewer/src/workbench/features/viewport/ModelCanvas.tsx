import { Canvas, useThree } from '@react-three/fiber'
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import type { Bounds3 } from '../../contracts'
import { NavigationControls } from './NavigationControls'
import type { LiveViewportSource } from './agentScreen'
import type { RotationMode } from './navigation'

interface ModelCanvasProps {
  artifactBytes: ArrayBuffer
  rotationMode: RotationMode
  boundsHint: Bounds3 | null
  fitRequest: number
  frameSelectedRequest: number
  onReady(): void
  registerLiveViewport(source: (() => LiveViewportSource) | null): void
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

function geometryBounds(geometry: THREE.BufferGeometry): Bounds3 | null {
  geometry.computeBoundingBox()
  const box = geometry.boundingBox
  if (!box) return null
  return {
    min: [box.min.x, box.min.y, box.min.z],
    max: [box.max.x, box.max.y, box.max.z],
  }
}

export default function ModelCanvas({
  artifactBytes,
  rotationMode,
  boundsHint,
  fitRequest,
  frameSelectedRequest,
  onReady,
  registerLiveViewport,
}: ModelCanvasProps) {
  const geometry = useMemo(() => {
    const parsed = new STLLoader().parse(artifactBytes)
    parsed.computeVertexNormals()
    return parsed
  }, [artifactBytes])
  const bounds = useMemo(() => geometryBounds(geometry) ?? boundsHint, [boundsHint, geometry])

  useEffect(() => {
    onReady()
    return () => geometry.dispose()
  }, [geometry, onReady])

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
      <mesh geometry={geometry} castShadow receiveShadow>
        <meshStandardMaterial color="#d8a861" metalness={0.08} roughness={0.58} />
      </mesh>
      <NavigationControls
        rotationMode={rotationMode}
        visibleBounds={bounds}
        selectedBounds={bounds}
        fitRequest={fitRequest}
        frameSelectedRequest={frameSelectedRequest}
      />
      <LiveViewportBridge register={registerLiveViewport} />
    </Canvas>
  )
}

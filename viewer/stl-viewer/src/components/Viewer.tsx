import { useEffect, useMemo, useRef } from 'react'
import { Canvas } from '@react-three/fiber'
import { Grid } from '@react-three/drei'
import ViewportControls from './ViewportControls'
import type { ModelData, RotationMode, ViewerOccurrence } from '../types'
import * as THREE from 'three'

interface ViewerProps {
  models: ModelData[]
  activeName: string | null
  onActiveNameChange: (name: string | null) => void
  onModelActivate: (name: string, additive: boolean) => void
  fitRequest: number
  frameSelectedRequest: number
  rotationMode: RotationMode
}

function occurrenceRotation(occurrence: ViewerOccurrence): [number, number, number] {
  return [
    THREE.MathUtils.degToRad(occurrence.rotation[0]),
    THREE.MathUtils.degToRad(occurrence.rotation[1]),
    THREE.MathUtils.degToRad(occurrence.rotation[2]),
  ]
}

function ModelComponent({
  model,
  isActive,
  onClick,
}: {
  model: ModelData
  isActive: boolean
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
            geometry={model.geometry}
            onClick={(event) => {
              if (event.delta > 4) return
              event.stopPropagation()
              onClick(model.partId, event.nativeEvent.ctrlKey || event.nativeEvent.metaKey)
            }}
          >
            <meshStandardMaterial
              color={isActive ? model.color : '#8d99ae'}
              metalness={0.15}
              roughness={0.6}
              emissive={isActive ? '#17324a' : '#000000'}
              emissiveIntensity={isActive ? 0.25 : 0}
            />
          </mesh>
          <lineSegments geometry={edgeGeometry}>
            <lineBasicMaterial color={model.wireframeColor} />
          </lineSegments>
        </group>
      ))}
    </group>
  )
}

function SceneContent({ models, activeName, onModelActivate, fitRequest, frameSelectedRequest, rotationMode }: ViewerProps) {
  return (
    <>
      <ambientLight intensity={0.55} />
      <directionalLight position={[80, 120, 80]} intensity={1.1} />
      <directionalLight position={[-80, -60, -70]} intensity={0.35} color="#f4d35e" />
      <hemisphereLight color="#d8f3ff" groundColor="#253040" intensity={0.45} />
      <Grid
        rotation={[Math.PI / 2, 0, 0]}
        args={[320, 32]}
        cellColor="#334155"
        sectionColor="#64748b"
        fadeDistance={700}
        fadeStrength={1}
      />
      <axesHelper args={[70]} />
      {models.map((model) => (
        <ModelComponent key={model.partId} model={model} isActive={model.partId === activeName} onClick={onModelActivate} />
      ))}
      <ViewportControls
        models={models}
        activeName={activeName}
        fitRequest={fitRequest}
        frameSelectedRequest={frameSelectedRequest}
        rotationMode={rotationMode}
      />
    </>
  )
}

export default function Viewer(props: ViewerProps) {
  const pointerDownRef = useRef<{ x: number; y: number } | null>(null)
  const maxPointerDeltaRef = useRef(0)

  return (
    <div style={{ width: '100%', height: '100%', minHeight: 0 }}>
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
          if (event.type === 'click' && maxPointerDeltaRef.current <= 4) {
            props.onActiveNameChange(null)
          }
        }}
      >
        <SceneContent {...props} />
      </Canvas>
      {props.models.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-title">No visible parts</div>
        </div>
      ) : null}
    </div>
  )
}

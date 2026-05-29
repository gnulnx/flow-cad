import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'
import type { ModelData, ViewerOccurrence } from '../types'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'

interface ViewerProps {
  models: ModelData[]
  activeName: string | null
  onActiveNameChange: (name: string | null) => void
  fitRequest: number
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

function ModelComponent({ model, isActive, onClick }: { model: ModelData; isActive: boolean; onClick: (name: string) => void }) {
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
              event.stopPropagation()
              onClick(model.partId)
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

function SceneContent({ models, activeName, onActiveNameChange, fitRequest }: ViewerProps) {
  const { camera } = useThree()
  const controlsRef = useRef<OrbitControlsImpl>(null)

  useEffect(() => {
    const perspectiveCamera = camera as THREE.PerspectiveCamera

    if (models.length === 0) {
      perspectiveCamera.position.set(140, 110, 140)
      perspectiveCamera.near = 0.1
      perspectiveCamera.far = 2000
      perspectiveCamera.lookAt(0, 0, 0)
      controlsRef.current?.target.set(0, 0, 0)
      controlsRef.current?.update()
      perspectiveCamera.updateProjectionMatrix()
      return
    }

    const box = new THREE.Box3()
    models.forEach((model) => {
      model.geometry.computeBoundingBox()
      if (model.geometry.boundingBox) {
        model.occurrences.forEach((occurrence) => {
          box.union(model.geometry.boundingBox!.clone().applyMatrix4(occurrenceMatrix(occurrence)))
        })
      }
    })

    const center = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3())
    const maxDim = Math.max(size.x, size.y, size.z, 1)
    const distance = (maxDim / (2 * Math.tan(THREE.MathUtils.degToRad(perspectiveCamera.fov / 2)))) * 1.85
    const viewDirection = new THREE.Vector3(1, 0.9, 1).normalize()

    perspectiveCamera.position.copy(center).addScaledVector(viewDirection, distance)
    perspectiveCamera.near = Math.max(distance / 1000, 0.01)
    perspectiveCamera.far = distance * 1000
    perspectiveCamera.lookAt(center)
    camera.updateProjectionMatrix()
    controlsRef.current?.target.copy(center)
    controlsRef.current?.update()
  }, [camera, fitRequest])

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
        <ModelComponent key={model.partId} model={model} isActive={model.partId === activeName} onClick={onActiveNameChange} />
      ))}
      <OrbitControls ref={controlsRef} enableDamping dampingFactor={0.08} makeDefault />
    </>
  )
}

export default function Viewer(props: ViewerProps) {
  return (
    <div style={{ width: '100%', height: '100%', minHeight: 0 }}>
      <Canvas camera={{ position: [140, 110, 140], fov: 45 }} shadows style={{ width: '100%', height: '100%' }}>
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

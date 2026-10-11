import { useMemo } from 'react'
import { Environment, Lightformer } from '@react-three/drei'
import * as THREE from 'three'
import type { Bounds3 } from '../../contracts'

export function showroomLayout(bounds: Bounds3 | null) {
  const min = bounds?.min ?? [-50, -50, 0]
  const max = bounds?.max ?? [50, 50, 100]
  const size = Math.max(...max.map((value, index) => value - min[index]), 1)
  return { size, center: min.map((value, index) => (value + max[index]) / 2) as [number, number, number], floor: min[2] - size * .003 }
}

/** Presentation objects never participate in picking, model bounds, or measurement. */
export function Showroom({ bounds }: { bounds: Bounds3 | null }) {
  const { size, center, floor } = showroomLayout(bounds)
  const target = useMemo(() => new THREE.Object3D(), [])
  target.position.set(...center)
  const position = (x: number, y: number, z: number): [number, number, number] =>
    [center[0] + x * size, center[1] + y * size, center[2] + z * size]
  return <>
    <color attach="background" args={['#182330']} />
    <primitive object={target} />
    <hemisphereLight args={['#eaf2ff', '#697583', 2.1]} position={[0, 0, 1]} />
    <directionalLight position={position(-1, -1.5, 2)} target={target} color="#fff0dc" intensity={3.2}
      castShadow shadow-mapSize={[2048, 2048]} shadow-bias={-.0002} shadow-normalBias={size * .001}
      shadow-camera-left={-size} shadow-camera-right={size} shadow-camera-top={size} shadow-camera-bottom={-size}
      shadow-camera-near={size * .01} shadow-camera-far={size * 7} shadow-radius={4} />
    <directionalLight position={position(1.5, -.5, .7)} target={target} color="#b5deff" intensity={1.8} />
    <directionalLight position={position(.5, 1.5, 1.4)} target={target} color="#84d9ff" intensity={3} />
    <Environment resolution={128} frames={1}>
      <Lightformer position={[0, -5, 5]} rotation={[Math.PI / 4, 0, 0]} scale={[10, 4, 1]} intensity={2} />
      <Lightformer position={[-5, 0, 3]} rotation={[0, Math.PI / 2, 0]} scale={[3, 8, 1]} color="#c2e5ff" intensity={2} />
      <Lightformer position={[5, 3, 4]} rotation={[0, -Math.PI / 2, 0]} scale={[3, 8, 1]} color="#ffe4b8" intensity={2} />
    </Environment>
    <mesh position={[center[0], center[1], floor]} receiveShadow raycast={() => undefined}>
      <planeGeometry args={[size * 200, size * 200]} />
      <meshStandardMaterial color="#303d4b" roughness={.72} metalness={.15} side={THREE.DoubleSide} />
    </mesh>
  </>
}

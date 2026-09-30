import { Line } from '@react-three/drei'
import type { Point3 } from '../../contracts'
import { isMeasurementStale, type MeasurementResult, type SnapCandidate } from './measurement'

interface MeasurementSceneProps {
  hover: SnapCandidate | null
  start: SnapCandidate | null
  measurements: MeasurementResult[]
  currentPartUuid: string | null
  currentArtifactRevision: string | null
}

export function MeasurementScene({
  hover,
  start,
  measurements,
  currentPartUuid,
  currentArtifactRevision,
}: MeasurementSceneProps) {
  return (
    <group renderOrder={50}>
      {hover?.edge ? <ExactLine start={hover.edge.startMm} end={hover.edge.endMm} color={qualityColor(hover.quality)} opacity={0.78} /> : null}
      {hover ? <ExactMarker point={hover.pointMm} color={qualityColor(hover.quality)} scale={1.7} /> : null}
      {start ? <ExactMarker point={start.pointMm} color={qualityColor(start.quality)} scale={2.1} /> : null}
      {start && hover ? <ExactLine start={start.pointMm} end={hover.pointMm} color="#56ed83" opacity={1} width={3.5} /> : null}
      {measurements.map((measurement) => measurement.hidden ? null : (
        <ExactLine
          key={measurement.id}
          start={measurement.startMm}
          end={measurement.endMm}
          color={isMeasurementStale(measurement, currentPartUuid, currentArtifactRevision) ? '#e6b66a' : '#56ed83'}
          width={3.5}
          opacity={0.95}
        />
      ))}
    </group>
  )
}

function qualityColor(quality: 'Exact' | 'Approximate') {
  return quality === 'Exact' ? '#79cbd1' : '#e6b66a'
}

function ExactMarker({ point, color, scale }: { point: Point3; color: string; scale: number }) {
  return (
    <mesh position={point} scale={scale} renderOrder={52}>
      <sphereGeometry args={[1, 12, 8]} />
      <meshBasicMaterial color={color} depthTest={false} toneMapped={false} />
    </mesh>
  )
}

export function ExactLine({ start, end, color, opacity, width = 2 }: {
  start: Point3
  end: Point3
  color: string
  opacity: number
  width?: number
}) {
  return <Line points={[start, end]} color={color} lineWidth={width}
    transparent={opacity < 1} opacity={opacity} depthTest={false}
    toneMapped={false} renderOrder={51} raycast={() => undefined} />
}

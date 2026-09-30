import { Html } from '@react-three/drei'
import type { Bounds3, Point3 } from '../../contracts'
import { boundsDimensions } from './DimensionsPanel'
import { ExactLine } from './MeasurementScene'
import { formatMm } from './measurement'

export function DimensionsScene({ bounds }: { bounds: Bounds3 | null }) {
  if (!bounds) return null
  const size = boundsDimensions(bounds)
  const offset = Math.max(...size, 1) * .09
  return <group>{size.map((length, axis) => {
    const start = bounds.min.map((v, i) => v - (i === axis ? 0 : offset)) as Point3
    const end = [...start] as Point3
    end[axis] = bounds.max[axis]
    const center = start.map((v, i) => (v + end[i]) / 2) as Point3
    const color = ['#f39987', '#9ce39c', '#85c5ff'][axis]
    return <group key={axis}>
      <ExactLine start={start} end={end} color={color} opacity={.9} />
      {[start, end].map((point, index) => {
        const a = [...point] as Point3, b = [...point] as Point3
        a[(axis + 1) % 3] -= offset * .25; b[(axis + 1) % 3] += offset * .25
        return <ExactLine key={index} start={a} end={b} color={color} opacity={.9} />
      })}
      <Html position={center} center style={{ pointerEvents: 'none' }}><span className="dimension-callout" style={{ color }}>{['X', 'Y', 'Z'][axis]} {formatMm(length)}</span></Html>
    </group>
  })}</group>
}

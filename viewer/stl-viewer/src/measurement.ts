import * as THREE from 'three'
import type { BufferGeometry } from 'three'
import type { SnapFeature, SnapFeatureKind } from './types'

export interface MeasurementTarget {
  id: string
  kind: SnapFeatureKind
  label: string
  point: THREE.Vector3
  partId?: string
  occurrenceName?: string
  segment?: {
    start: THREE.Vector3
    end: THREE.Vector3
  }
  ringPoints?: THREE.Vector3[]
  length?: number
  radius?: number
}

export interface ResolvedMeasurement {
  label: string
  startPoint: THREE.Vector3
  endPoint: THREE.Vector3
  distance: number
  delta: THREE.Vector3
}

const EPSILON = 1e-9
const MAX_MESH_VERTICES = 1200
const MAX_MESH_EDGES = 1800

export const SNAP_KIND_PRIORITY: Record<SnapFeatureKind, number> = {
  circle_center: 0,
  vertex: 1,
  line_edge: 2,
  edge_midpoint: 3,
  face_point: 5,
  free_point: 6,
}

export function labelForFeatureKind(kind: SnapFeatureKind) {
  if (kind === 'circle_center') return 'Hole Center'
  if (kind === 'vertex') return 'Endpoint'
  if (kind === 'edge_midpoint') return 'Edge Midpoint'
  if (kind === 'line_edge') return 'Edge'
  if (kind === 'face_point') return 'Face Point'
  return 'Free Point'
}

export function vectorFromTuple(tuple: [number, number, number]) {
  return new THREE.Vector3(tuple[0], tuple[1], tuple[2])
}

export function targetFromFeature(
  feature: SnapFeature,
  matrix: THREE.Matrix4,
  partId: string,
  occurrenceName: string,
): MeasurementTarget | null {
  const pointTuple = feature.point ?? feature.start ?? feature.edge_start
  if (!pointTuple) return null

  const point = vectorFromTuple(pointTuple).applyMatrix4(matrix)
  const startTuple = feature.start ?? feature.edge_start
  const endTuple = feature.end ?? feature.edge_end
  const segment = startTuple && endTuple
    ? {
        start: vectorFromTuple(startTuple).applyMatrix4(matrix),
        end: vectorFromTuple(endTuple).applyMatrix4(matrix),
      }
    : undefined
  const ringPoints = feature.ring_points?.map((point) => vectorFromTuple(point).applyMatrix4(matrix))

  return {
    id: `${partId}:${occurrenceName}:${feature.id}`,
    kind: feature.kind,
    label: feature.label || labelForFeatureKind(feature.kind),
    point,
    partId,
    occurrenceName,
    segment,
    ringPoints,
    length: feature.length,
    radius: feature.radius,
  }
}

export function freePointTarget(point: THREE.Vector3): MeasurementTarget {
  return {
    id: `free:${point.x.toFixed(3)}:${point.y.toFixed(3)}:${point.z.toFixed(3)}`,
    kind: 'free_point',
    label: 'Free Point',
    point: point.clone(),
  }
}

export function resolveMeasurement(start: MeasurementTarget, end: MeasurementTarget): ResolvedMeasurement {
  const closest = closestMeasurementPoints(start, end)
  const delta = closest.end.clone().sub(closest.start)
  return {
    label: `${start.label} -> ${end.label}`,
    startPoint: closest.start,
    endPoint: closest.end,
    distance: delta.length(),
    delta,
  }
}

export function resolveEdgeLength(target: MeasurementTarget): ResolvedMeasurement | null {
  if (!target.segment) return null
  const delta = target.segment.end.clone().sub(target.segment.start)
  return {
    label: 'Edge Length',
    startPoint: target.segment.start.clone(),
    endPoint: target.segment.end.clone(),
    distance: target.length ?? delta.length(),
    delta,
  }
}

export function formatMm(value: number) {
  const rounded = Math.abs(value) < 0.005 ? 0 : value
  return `${rounded.toFixed(Math.abs(rounded) >= 100 ? 1 : 2)} mm`
}

export function buildMeshSnapFeatures(geometry: BufferGeometry): SnapFeature[] {
  const edgeGeometry = new THREE.EdgesGeometry(geometry, 20)
  const position = edgeGeometry.attributes.position
  if (!position) {
    edgeGeometry.dispose()
    return []
  }

  const vertexMap = new Map<string, [number, number, number]>()
  const features: SnapFeature[] = []

  for (let index = 0; index < position.count; index += 1) {
    const point: [number, number, number] = [
      position.getX(index),
      position.getY(index),
      position.getZ(index),
    ]
    const key = pointKey(point)
    if (!vertexMap.has(key) && vertexMap.size < MAX_MESH_VERTICES) {
      vertexMap.set(key, point)
    }
  }

  features.push(...Array.from(vertexMap.entries()).map(([key, point], index) => ({
    id: `mesh-vertex:${index}:${key}`,
    kind: 'vertex',
    label: 'Endpoint',
    point,
  })))

  const edgeMap = new Map<string, [[number, number, number], [number, number, number]]>()
  for (let index = 0; index + 1 < position.count && edgeMap.size < MAX_MESH_EDGES; index += 2) {
    const start: [number, number, number] = [
      position.getX(index),
      position.getY(index),
      position.getZ(index),
    ]
    const end: [number, number, number] = [
      position.getX(index + 1),
      position.getY(index + 1),
      position.getZ(index + 1),
    ]
    addMeshEdge(edgeMap, pointKey(start), start, pointKey(end), end)
  }

  Array.from(edgeMap.entries()).forEach(([key, [start, end]], index) => {
    const startVector = vectorFromTuple(start)
    const endVector = vectorFromTuple(end)
    const midpoint = startVector.clone().add(endVector).multiplyScalar(0.5)
    const length = startVector.distanceTo(endVector)
    features.push({
      id: `mesh-edge:${index}:${key}`,
      kind: 'line_edge',
      label: 'Edge',
      point: [midpoint.x, midpoint.y, midpoint.z],
      start,
      end,
      length,
    })
    features.push({
      id: `mesh-edge-midpoint:${index}:${key}`,
      kind: 'edge_midpoint',
      label: 'Edge Midpoint',
      point: [midpoint.x, midpoint.y, midpoint.z],
      edge_start: start,
      edge_end: end,
    })
  })

  edgeGeometry.dispose()
  return features
}

function addMeshEdge(
  edgeMap: Map<string, [[number, number, number], [number, number, number]]>,
  aKey: string,
  a: [number, number, number],
  bKey: string,
  b: [number, number, number],
) {
  if (aKey === bKey) return
  const edgeKey = aKey < bKey ? `${aKey}|${bKey}` : `${bKey}|${aKey}`
  if (!edgeMap.has(edgeKey)) {
    edgeMap.set(edgeKey, aKey < bKey ? [a, b] : [b, a])
  }
}

function pointKey(point: [number, number, number]) {
  return point.map((value) => value.toFixed(3)).join(':')
}

function closestMeasurementPoints(start: MeasurementTarget, end: MeasurementTarget) {
  if (start.segment && end.segment) {
    return closestPointsBetweenSegments(start.segment.start, start.segment.end, end.segment.start, end.segment.end)
  }
  if (start.segment) {
    return {
      start: closestPointOnSegment(start.segment.start, start.segment.end, end.point),
      end: end.point.clone(),
    }
  }
  if (end.segment) {
    return {
      start: start.point.clone(),
      end: closestPointOnSegment(end.segment.start, end.segment.end, start.point),
    }
  }
  return {
    start: start.point.clone(),
    end: end.point.clone(),
  }
}

function closestPointOnSegment(start: THREE.Vector3, end: THREE.Vector3, point: THREE.Vector3) {
  const segment = end.clone().sub(start)
  const lengthSq = segment.lengthSq()
  if (lengthSq < EPSILON) return start.clone()
  const t = THREE.MathUtils.clamp(point.clone().sub(start).dot(segment) / lengthSq, 0, 1)
  return start.clone().addScaledVector(segment, t)
}

function closestPointsBetweenSegments(
  p1: THREE.Vector3,
  q1: THREE.Vector3,
  p2: THREE.Vector3,
  q2: THREE.Vector3,
) {
  const d1 = q1.clone().sub(p1)
  const d2 = q2.clone().sub(p2)
  const r = p1.clone().sub(p2)
  const a = d1.dot(d1)
  const e = d2.dot(d2)
  const f = d2.dot(r)
  let s = 0
  let t = 0

  if (a <= EPSILON && e <= EPSILON) {
    return { start: p1.clone(), end: p2.clone() }
  }
  if (a <= EPSILON) {
    t = THREE.MathUtils.clamp(f / e, 0, 1)
  } else {
    const c = d1.dot(r)
    if (e <= EPSILON) {
      s = THREE.MathUtils.clamp(-c / a, 0, 1)
    } else {
      const b = d1.dot(d2)
      const denom = a * e - b * b
      if (denom !== 0) {
        s = THREE.MathUtils.clamp((b * f - c * e) / denom, 0, 1)
      }
      const tNom = b * s + f
      if (tNom < 0) {
        t = 0
        s = THREE.MathUtils.clamp(-c / a, 0, 1)
      } else if (tNom > e) {
        t = 1
        s = THREE.MathUtils.clamp((b - c) / a, 0, 1)
      } else {
        t = tNom / e
      }
    }
  }

  return {
    start: p1.clone().addScaledVector(d1, s),
    end: p2.clone().addScaledVector(d2, t),
  }
}

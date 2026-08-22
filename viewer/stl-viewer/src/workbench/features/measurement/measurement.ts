import type { ExactFeature, ExactFeatureKind, Point3 } from '../../contracts'

export interface ScreenPoint {
  x: number
  y: number
  depth: number
  visible: boolean
}

export type PointProjector = (pointMm: Point3) => ScreenPoint | null

export interface MeasurementProjectionSource {
  createProjector(): PointProjector
}

export interface SnapCandidate {
  featureId: string
  kind: ExactFeatureKind
  label: string
  pointMm: Point3
  screen: ScreenPoint
  distancePx: number
  edge?: {
    startMm: Point3
    endMm: Point3
    lengthMm: number
  }
}

export interface MeasurementBinding {
  partUuid: string
  artifactRevision: string
  featureIds: string[]
}

export interface MeasurementResult {
  id: string
  kind: 'distance' | 'edge_length'
  title: string
  quality: 'Exact' | 'Approximate'
  startMm: Point3
  endMm: Point3
  totalMm: number
  deltaMm: Point3
  binding: MeasurementBinding
  hidden: boolean
  pinned: boolean
  offsetPx: [number, number]
}

const KIND_PRIORITY: Record<ExactFeatureKind, number> = {
  vertex: 0,
  circle_center: 1,
  edge_midpoint: 2,
  line_edge: 3,
}

export const DEFAULT_SNAP_RADIUS_PX = 16

export function featureLabel(kind: ExactFeatureKind): string {
  if (kind === 'vertex') return 'Exact vertex'
  if (kind === 'edge_midpoint') return 'Exact edge midpoint'
  if (kind === 'circle_center') return 'Exact circle center'
  return 'Exact line edge'
}

export function findScreenSpaceSnap(
  pointer: { x: number; y: number },
  features: ExactFeature[],
  project: PointProjector,
  radiusPx = DEFAULT_SNAP_RADIUS_PX,
): SnapCandidate | null {
  let best: SnapCandidate | null = null
  for (const feature of features) {
    const candidate = candidateForFeature(pointer, feature, project)
    if (!candidate || candidate.distancePx > radiusPx) continue
    if (!best
      || candidate.distancePx < best.distancePx
      || (candidate.distancePx === best.distancePx && KIND_PRIORITY[candidate.kind] < KIND_PRIORITY[best.kind])
      || (candidate.distancePx === best.distancePx
        && KIND_PRIORITY[candidate.kind] === KIND_PRIORITY[best.kind]
        && candidate.featureId.localeCompare(best.featureId) < 0)) {
      best = candidate
    }
  }
  return best
}

function candidateForFeature(
  pointer: { x: number; y: number },
  feature: ExactFeature,
  project: PointProjector,
): SnapCandidate | null {
  if (feature.kind === 'line_edge') {
    if (!feature.startMm || !feature.endMm || feature.lengthMm === undefined) return null
    const start = project(feature.startMm)
    const end = project(feature.endMm)
    if (!start?.visible || !end?.visible) return null
    const nearest = nearestPointOnSegment(pointer, start, end)
    return {
      featureId: feature.id,
      kind: feature.kind,
      label: `${featureLabel(feature.kind)} · ${formatMm(feature.lengthMm)}`,
      pointMm: lerpPoint(feature.startMm, feature.endMm, nearest.t),
      screen: { x: nearest.x, y: nearest.y, depth: start.depth + (end.depth - start.depth) * nearest.t, visible: true },
      distancePx: nearest.distance,
      edge: { startMm: feature.startMm, endMm: feature.endMm, lengthMm: feature.lengthMm },
    }
  }

  const point = feature.pointMm
  if (!point) return null
  const screen = project(point)
  if (!screen?.visible) return null
  return {
    featureId: feature.id,
    kind: feature.kind,
    label: featureLabel(feature.kind),
    pointMm: point,
    screen,
    distancePx: Math.hypot(pointer.x - screen.x, pointer.y - screen.y),
  }
}

export function createDistanceMeasurement(
  id: string,
  start: SnapCandidate,
  end: SnapCandidate,
  binding: Omit<MeasurementBinding, 'featureIds'>,
): MeasurementResult {
  const deltaMm = subtract(end.pointMm, start.pointMm)
  return {
    id,
    kind: 'distance',
    title: `${featureLabel(start.kind)} to ${featureLabel(end.kind)}`,
    quality: 'Exact',
    startMm: start.pointMm,
    endMm: end.pointMm,
    totalMm: length(deltaMm),
    deltaMm,
    binding: { ...binding, featureIds: [start.featureId, end.featureId] },
    hidden: false,
    pinned: false,
    offsetPx: [0, 0],
  }
}

export function createEdgeLengthMeasurement(
  id: string,
  target: SnapCandidate,
  binding: Omit<MeasurementBinding, 'featureIds'>,
): MeasurementResult | null {
  if (!target.edge) return null
  return {
    id,
    kind: 'edge_length',
    title: 'Exact edge length',
    quality: 'Exact',
    startMm: target.edge.startMm,
    endMm: target.edge.endMm,
    totalMm: target.edge.lengthMm,
    deltaMm: subtract(target.edge.endMm, target.edge.startMm),
    binding: { ...binding, featureIds: [target.featureId] },
    hidden: false,
    pinned: false,
    offsetPx: [0, 0],
  }
}

export function isMeasurementStale(
  measurement: MeasurementResult,
  partUuid: string | null,
  artifactRevision: string | null,
): boolean {
  return measurement.binding.partUuid !== partUuid
    || measurement.binding.artifactRevision !== artifactRevision
}

export function formatMm(value: number): string {
  const clean = Math.abs(value) < 0.0005 ? 0 : value
  return `${clean.toFixed(Math.abs(clean) >= 100 ? 1 : 2)} mm`
}

function nearestPointOnSegment(
  pointer: { x: number; y: number },
  start: ScreenPoint,
  end: ScreenPoint,
) {
  const dx = end.x - start.x
  const dy = end.y - start.y
  const denominator = dx * dx + dy * dy
  const t = denominator <= Number.EPSILON
    ? 0
    : Math.max(0, Math.min(1, ((pointer.x - start.x) * dx + (pointer.y - start.y) * dy) / denominator))
  const x = start.x + dx * t
  const y = start.y + dy * t
  return { x, y, t, distance: Math.hypot(pointer.x - x, pointer.y - y) }
}

function lerpPoint(start: Point3, end: Point3, t: number): Point3 {
  return [
    start[0] + (end[0] - start[0]) * t,
    start[1] + (end[1] - start[1]) * t,
    start[2] + (end[2] - start[2]) * t,
  ]
}

function subtract(end: Point3, start: Point3): Point3 {
  return [end[0] - start[0], end[1] - start[1], end[2] - start[2]]
}

function length(point: Point3): number {
  return Math.hypot(point[0], point[1], point[2])
}

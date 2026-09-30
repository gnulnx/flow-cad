import type { ExactFeature, ExactFeatureKind, Point3 } from '../../contracts'

export type MeasurementQuality = 'Exact' | 'Approximate'
export type MeasurementSnapKind = ExactFeatureKind | 'free_point'

export interface MeasurementFeature extends Omit<ExactFeature, 'quality' | 'source'> {
  quality: 'exact' | 'approximate'
  source: 'step_topology' | 'mesh_sample'
}

export interface ScreenPoint {
  x: number
  y: number
  depth: number
  visible: boolean
  clipW?: number
}

export type PointProjector = (pointMm: Point3) => ScreenPoint | null

export interface MeasurementProjectionSource {
  createProjector(): PointProjector
  pickPlanePoint?(x: number, y: number, plane: MeasurementPlane, anchor: Point3): SnapCandidate | null
}

export type MeasurementPlane = 'view' | 'xy' | 'xz' | 'yz'
export type MeasurementMode = 'distance' | 'edge_length'
export type SnapFilter = 'all' | 'circle_center' | 'vertex' | 'line_edge'

export interface ApproximateMeasurementSource {
  partUuid: string
  artifactRevision: string
  features: MeasurementFeature[]
  pickFreePoint(clientX: number, clientY: number): SnapCandidate | null
}

export interface SnapCandidate {
  featureId: string
  kind: MeasurementSnapKind
  quality: MeasurementQuality
  label: string
  pointMm: Point3
  screen: ScreenPoint
  distancePx: number
  edge?: {
    startMm: Point3
    endMm: Point3
    lengthMm: number
  }
  radiusMm?: number
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
  quality: MeasurementQuality
  startMm: Point3
  endMm: Point3
  totalMm: number
  deltaMm: Point3
  binding: MeasurementBinding
  hidden: boolean
  pinned: boolean
  offsetPx: [number, number]
}

const KIND_PRIORITY: Record<MeasurementSnapKind, number> = {
  vertex: 0,
  circle_center: 1,
  edge_midpoint: 2,
  line_edge: 3,
  free_point: 4,
}

const QUALITY_PRIORITY: Record<MeasurementQuality, number> = { Exact: 0, Approximate: 1 }

export const DEFAULT_SNAP_RADIUS_PX = 16

export function featureLabel(kind: MeasurementSnapKind, quality: MeasurementQuality = 'Exact'): string {
  if (kind === 'vertex') return `${quality} vertex`
  if (kind === 'edge_midpoint') return `${quality} edge midpoint`
  if (kind === 'circle_center') return `${quality} circle center`
  if (kind === 'free_point') return `${quality} free point`
  return `${quality} line edge`
}

export function findScreenSpaceSnap(
  pointer: { x: number; y: number },
  features: readonly (MeasurementFeature | ExactFeature)[],
  project: PointProjector,
  radiusPx = DEFAULT_SNAP_RADIUS_PX,
  filter: SnapFilter = 'all',
): SnapCandidate | null {
  let best: SnapCandidate | null = null
  for (const feature of features) {
    if (filter !== 'all' && feature.kind !== filter) continue
    const candidate = candidateForFeature(pointer, feature, project)
    if (!candidate || candidate.distancePx > radiusPx) continue
    if (!best
      || QUALITY_PRIORITY[candidate.quality] < QUALITY_PRIORITY[best.quality]
      || (candidate.quality === best.quality && snapScore(candidate) < snapScore(best))) {
      best = candidate
    }
  }
  return best
}

// Point targets need a small preference over edges passing through them.
// Otherwise floating-point pixel differences make corners almost unpickable.
function snapScore(candidate: SnapCandidate): number {
  return candidate.distancePx + (candidate.kind === 'line_edge' ? 5 : 0)
    + candidate.screen.depth * 0.0001 + KIND_PRIORITY[candidate.kind] * 0.000001
}

function candidateForFeature(
  pointer: { x: number; y: number },
  feature: MeasurementFeature | ExactFeature,
  project: PointProjector,
): SnapCandidate | null {
  if (feature.kind === 'line_edge') {
    if (!feature.startMm || !feature.endMm || feature.lengthMm === undefined) return null
    const start = project(feature.startMm)
    const end = project(feature.endMm)
    if (!start?.visible || !end?.visible) return null
    const nearest = nearestPointOnSegment(pointer, start, end)
    const t = perspectiveSegmentParameter(nearest.t, start.clipW ?? 1, end.clipW ?? 1)
    const quality = feature.quality === 'exact' ? 'Exact' : 'Approximate'
    return {
      featureId: feature.id,
      kind: feature.kind,
      quality,
      label: `${featureLabel(feature.kind, quality)} · ${formatMm(feature.lengthMm)}`,
      pointMm: lerpPoint(feature.startMm, feature.endMm, t),
      screen: { x: nearest.x, y: nearest.y, depth: start.depth + (end.depth - start.depth) * nearest.t, visible: true },
      distancePx: nearest.distance,
      edge: { startMm: feature.startMm, endMm: feature.endMm, lengthMm: feature.lengthMm },
    }
  }

  const point = feature.pointMm
  if (!point) return null
  const screen = project(point)
  if (!screen?.visible) return null
  const quality = feature.quality === 'exact' ? 'Exact' : 'Approximate'
  return {
    featureId: feature.id,
    kind: feature.kind,
    quality,
    label: featureLabel(feature.kind, quality),
    pointMm: point,
    radiusMm: feature.radiusMm,
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
  const quality: MeasurementQuality = start.quality === 'Exact' && end.quality === 'Exact' ? 'Exact' : 'Approximate'
  return {
    id,
    kind: 'distance',
    title: `${start.label.split(' · ')[0]} to ${end.label.split(' · ')[0]}`,
    quality,
    startMm: start.pointMm,
    endMm: end.pointMm,
    totalMm: length(deltaMm),
    deltaMm,
    binding: { ...binding, featureIds: [anchorFeatureId(start), anchorFeatureId(end)] },
    hidden: false,
    pinned: false,
    offsetPx: [0, 0],
  }
}

function anchorFeatureId(target: SnapCandidate): string {
  return target.kind === 'line_edge'
    ? `${target.featureId}@${target.pointMm.map((value) => value.toFixed(6)).join(',')}`
    : target.featureId
}

export function perspectiveSegmentParameter(screenT: number, startW: number, endW: number): number {
  return (screenT / endW) / ((1 - screenT) / startW + screenT / endW)
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
    title: `${target.quality} edge length`,
    quality: target.quality,
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

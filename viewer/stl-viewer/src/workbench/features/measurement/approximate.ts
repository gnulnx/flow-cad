import type { Point3, WorkbenchOccurrence } from '../../contracts'
import { transformPoint } from '../viewport/assembly'
import type { MeasurementFeature } from './measurement'

export const MAX_APPROXIMATE_VERTICES = 1_200
export const MAX_APPROXIMATE_EDGES = 1_800
export const MAX_APPROXIMATE_PICK_TRIANGLES = 2_400

export interface ApproximateMeshFeatureSet {
  features: MeasurementFeature[]
  pickPositions: Float32Array
  sourceVertexCount: number
  sampledVertexCount: number
  sampledEdgeCount: number
  sampledTriangleCount: number
}

export function deriveApproximateMeshFeatures(
  positions: ArrayLike<number>,
  occurrence: WorkbenchOccurrence,
): ApproximateMeshFeatureSet {
  const vertexCount = Math.floor(positions.length / 3)
  const triangleCount = Math.floor(vertexCount / 3)
  const features: MeasurementFeature[] = []
  const seenVertices = new Set<string>()
  const seenEdges = new Set<string>()

  for (const vertexIndex of sampleIndices(vertexCount, MAX_APPROXIMATE_VERTICES)) {
    const point = pointAt(positions, vertexIndex)
    const key = pointKey(point)
    if (seenVertices.has(key)) continue
    seenVertices.add(key)
    features.push({
      id: `mesh_vertex:${vertexIndex}`,
      kind: 'vertex',
      quality: 'approximate',
      source: 'mesh_sample',
      pointMm: transformPoint(point, occurrence),
    })
  }
  const sampledVertexCount = features.length

  const edgeTriangleLimit = Math.ceil(MAX_APPROXIMATE_EDGES / 3)
  for (const triangleIndex of sampleIndices(triangleCount, edgeTriangleLimit)) {
    const vertices = [
      pointAt(positions, triangleIndex * 3),
      pointAt(positions, triangleIndex * 3 + 1),
      pointAt(positions, triangleIndex * 3 + 2),
    ] as const
    for (const [edgeIndex, [start, end]] of ([[vertices[0], vertices[1]], [vertices[1], vertices[2]], [vertices[2], vertices[0]]] as const).entries()) {
      if (features.length - sampledVertexCount >= MAX_APPROXIMATE_EDGES) break
      const startKey = pointKey(start)
      const endKey = pointKey(end)
      if (startKey === endKey) continue
      const key = startKey < endKey ? `${startKey}|${endKey}` : `${endKey}|${startKey}`
      if (seenEdges.has(key)) continue
      seenEdges.add(key)
      const worldStart = transformPoint(start, occurrence)
      const worldEnd = transformPoint(end, occurrence)
      features.push({
        id: `mesh_edge:${triangleIndex}:${edgeIndex}`,
        kind: 'line_edge',
        quality: 'approximate',
        source: 'mesh_sample',
        startMm: worldStart,
        endMm: worldEnd,
        midpointMm: midpoint(worldStart, worldEnd),
        lengthMm: distance(worldStart, worldEnd),
      })
    }
  }

  const pickTriangleIndices = sampleIndices(triangleCount, MAX_APPROXIMATE_PICK_TRIANGLES)
  const pickPositions = new Float32Array(pickTriangleIndices.length * 9)
  let offset = 0
  for (const triangleIndex of pickTriangleIndices) {
    for (let vertex = 0; vertex < 3; vertex += 1) {
      const point = pointAt(positions, triangleIndex * 3 + vertex)
      pickPositions[offset++] = point[0]
      pickPositions[offset++] = point[1]
      pickPositions[offset++] = point[2]
    }
  }

  return {
    features,
    pickPositions,
    sourceVertexCount: vertexCount,
    sampledVertexCount,
    sampledEdgeCount: features.length - sampledVertexCount,
    sampledTriangleCount: pickTriangleIndices.length,
  }
}

function sampleIndices(count: number, limit: number): number[] {
  const sampleCount = Math.min(Math.max(0, count), limit)
  return Array.from({ length: sampleCount }, (_, index) => Math.min(
    count - 1,
    Math.floor(index * count / sampleCount),
  ))
}

function pointAt(positions: ArrayLike<number>, index: number): Point3 {
  const offset = index * 3
  return [Number(positions[offset]), Number(positions[offset + 1]), Number(positions[offset + 2])]
}

function pointKey(point: Point3): string {
  return point.map((value) => Math.round(value * 100_000)).join(':')
}

function midpoint(start: Point3, end: Point3): Point3 {
  return [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2, (start[2] + end[2]) / 2]
}

function distance(start: Point3, end: Point3): number {
  return Math.hypot(end[0] - start[0], end[1] - start[1], end[2] - start[2])
}

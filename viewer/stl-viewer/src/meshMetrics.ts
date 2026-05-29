import { Box3, Vector3, type BufferGeometry, type BufferAttribute } from 'three'

export interface MeshBounds {
  min: Vector3
  max: Vector3
  size: Vector3
  center: Vector3
}

export interface MeshQuality {
  isLikelyClosed: boolean
  boundaryEdgeCount: number
  nonManifoldEdgeCount: number
  degenerateTriangleCount: number
  warnings: string[]
}

export interface MeshMetrics {
  triangleCount: number
  bounds: MeshBounds
  volumeMm3: number
  volumeCm3: number
  surfaceAreaMm2: number
  surfaceAreaCm2: number
  quality: MeshQuality
}

interface TrianglePoints {
  ax: number
  ay: number
  az: number
  bx: number
  by: number
  bz: number
  cx: number
  cy: number
  cz: number
}

interface PositionAttribute {
  count: number
  getX(index: number): number
  getY(index: number): number
  getZ(index: number): number
}

const DEGENERATE_AREA_EPSILON = 1e-9

export function calculateMeshMetrics(geometry: BufferGeometry): MeshMetrics {
  const position = geometry.attributes.position
  if (!position) {
    throw new Error('Cannot calculate mesh metrics: geometry has no position attribute')
  }

  const boundsBox = new Box3().setFromBufferAttribute(position as BufferAttribute)
  const size = boundsBox.getSize(new Vector3())
  const center = boundsBox.getCenter(new Vector3())
  const edgeCounts = new Map<string, number>()

  let signedVolumeTimesSix = 0
  let surfaceAreaMm2 = 0
  let triangleCount = 0
  let degenerateTriangleCount = 0

  forEachTriangle(geometry, (triangle) => {
    triangleCount += 1
    signedVolumeTimesSix += signedTetrahedronVolumeTimesSix(triangle)
    const area = triangleArea(triangle)
    surfaceAreaMm2 += area
    if (area < DEGENERATE_AREA_EPSILON) {
      degenerateTriangleCount += 1
    }
    addTriangleEdges(edgeCounts, triangle)
  })

  const boundaryEdgeCount = Array.from(edgeCounts.values()).filter((count) => count === 1).length
  const nonManifoldEdgeCount = Array.from(edgeCounts.values()).filter((count) => count > 2).length
  const isLikelyClosed = triangleCount > 0 && boundaryEdgeCount === 0 && nonManifoldEdgeCount === 0
  const volumeMm3 = Math.abs(signedVolumeTimesSix / 6)
  const warnings = meshMetricWarnings({ triangleCount, isLikelyClosed, boundaryEdgeCount, nonManifoldEdgeCount, degenerateTriangleCount })

  return {
    triangleCount,
    bounds: {
      min: boundsBox.min.clone(),
      max: boundsBox.max.clone(),
      size,
      center,
    },
    volumeMm3,
    volumeCm3: volumeMm3 / 1000,
    surfaceAreaMm2,
    surfaceAreaCm2: surfaceAreaMm2 / 100,
    quality: {
      isLikelyClosed,
      boundaryEdgeCount,
      nonManifoldEdgeCount,
      degenerateTriangleCount,
      warnings,
    },
  }
}

export function estimateWeightGrams(volumeMm3: number, densityGPerCm3: number, infillFactor = 1) {
  return (volumeMm3 / 1000) * densityGPerCm3 * infillFactor
}

function meshMetricWarnings({
  triangleCount,
  isLikelyClosed,
  boundaryEdgeCount,
  nonManifoldEdgeCount,
  degenerateTriangleCount,
}: {
  triangleCount: number
  isLikelyClosed: boolean
  boundaryEdgeCount: number
  nonManifoldEdgeCount: number
  degenerateTriangleCount: number
}) {
  const warnings: string[] = []
  if (triangleCount === 0) {
    warnings.push('Mesh has no triangles.')
  }
  if (!isLikelyClosed) {
    warnings.push('Mesh is not closed; volume should be treated as an estimate.')
  }
  if (boundaryEdgeCount > 0) {
    warnings.push(`Mesh has ${boundaryEdgeCount.toLocaleString()} boundary edges.`)
  }
  if (nonManifoldEdgeCount > 0) {
    warnings.push(`Mesh has ${nonManifoldEdgeCount.toLocaleString()} non-manifold edges.`)
  }
  if (degenerateTriangleCount > 0) {
    warnings.push(`Mesh has ${degenerateTriangleCount.toLocaleString()} degenerate triangles.`)
  }
  return warnings
}

function forEachTriangle(geometry: BufferGeometry, callback: (triangle: TrianglePoints) => void) {
  const position = geometry.attributes.position
  if (!position) return

  if (geometry.index) {
    const indices = geometry.index.array
    for (let index = 0; index + 2 < indices.length; index += 3) {
      callback(triangleFromIndices(position, Number(indices[index]), Number(indices[index + 1]), Number(indices[index + 2])))
    }
    return
  }

  for (let index = 0; index + 2 < position.count; index += 3) {
    callback(triangleFromIndices(position, index, index + 1, index + 2))
  }
}

function triangleFromIndices(position: PositionAttribute, a: number, b: number, c: number): TrianglePoints {
  return {
    ax: position.getX(a),
    ay: position.getY(a),
    az: position.getZ(a),
    bx: position.getX(b),
    by: position.getY(b),
    bz: position.getZ(b),
    cx: position.getX(c),
    cy: position.getY(c),
    cz: position.getZ(c),
  }
}

function signedTetrahedronVolumeTimesSix(triangle: TrianglePoints) {
  return (
    triangle.ax * (triangle.by * triangle.cz - triangle.bz * triangle.cy)
    + triangle.bx * (triangle.cy * triangle.az - triangle.cz * triangle.ay)
    + triangle.cx * (triangle.ay * triangle.bz - triangle.az * triangle.by)
  )
}

function triangleArea(triangle: TrianglePoints) {
  const abx = triangle.bx - triangle.ax
  const aby = triangle.by - triangle.ay
  const abz = triangle.bz - triangle.az
  const acx = triangle.cx - triangle.ax
  const acy = triangle.cy - triangle.ay
  const acz = triangle.cz - triangle.az
  const crossX = aby * acz - abz * acy
  const crossY = abz * acx - abx * acz
  const crossZ = abx * acy - aby * acx
  return Math.sqrt(crossX * crossX + crossY * crossY + crossZ * crossZ) * 0.5
}

function addTriangleEdges(edgeCounts: Map<string, number>, triangle: TrianglePoints) {
  const a = pointKey(triangle.ax, triangle.ay, triangle.az)
  const b = pointKey(triangle.bx, triangle.by, triangle.bz)
  const c = pointKey(triangle.cx, triangle.cy, triangle.cz)
  addEdge(edgeCounts, a, b)
  addEdge(edgeCounts, b, c)
  addEdge(edgeCounts, c, a)
}

function addEdge(edgeCounts: Map<string, number>, a: string, b: string) {
  const key = a < b ? `${a}|${b}` : `${b}|${a}`
  edgeCounts.set(key, (edgeCounts.get(key) ?? 0) + 1)
}

function pointKey(x: number, y: number, z: number) {
  return `${x.toFixed(6)}:${y.toFixed(6)}:${z.toFixed(6)}`
}

import type { ArtifactState, Bounds3, ExactFeature, Point3, WorkbenchOccurrence, WorkbenchPart } from '../../contracts'

export type AssemblyLoadState = 'queued' | 'loading' | 'downloaded' | 'visible' | 'failed'

export interface AssemblyLoadPlanItem {
  key: string
  part: WorkbenchPart
  occurrences: WorkbenchOccurrence[]
  priority: number
}

export interface AssemblyLoadRecord {
  key: string
  partUuid: string
  contentHash: string
  state: AssemblyLoadState
  error: string | null
}

export type AssemblyLoadRecords = Record<string, AssemblyLoadRecord>

const IDENTITY_OCCURRENCE_SUFFIX = ':inspection'

export function resolveActiveAssemblyId(
  parts: WorkbenchPart[],
  preferred: string | null,
): string | null {
  if (preferred) return preferred
  const assemblyIds = parts.flatMap((part) => part.occurrences.map((occurrence) => occurrence.assemblyId))
  if (assemblyIds.includes('active')) return 'active'
  return assemblyIds[0] ?? null
}

export function planAssemblyLoads(
  parts: WorkbenchPart[],
  activeAssemblyId: string | null,
  selectedPartUuid: string | null,
): AssemblyLoadPlanItem[] {
  const assemblyId = resolveActiveAssemblyId(parts, activeAssemblyId)
  const plan: AssemblyLoadPlanItem[] = []
  for (const part of parts) {
    if (!part.displayArtifact || part.status === 'retired' || part.status === 'superseded') continue
    const selected = part.uuid === selectedPartUuid
    const occurrences = assemblyId
      ? part.occurrences.filter((occurrence) => occurrence.assemblyId === assemblyId)
      : part.occurrences
    if (part.role === 'reference' && !selected) continue
    if (occurrences.length === 0 && !selected) continue
    plan.push({
      key: `${part.uuid}:${part.displayArtifact.contentHash}`,
      part,
      occurrences: occurrences.length > 0 ? occurrences : [inspectionOccurrence(part.uuid, assemblyId)],
      priority: selected ? 0 : defaultPriority(part),
    })
  }
  return plan.sort((left, right) => left.priority - right.priority || left.part.key.localeCompare(right.part.key))
}

export function reconcileLoadRecords(
  records: AssemblyLoadRecords,
  plan: AssemblyLoadPlanItem[],
): AssemblyLoadRecords {
  const next = { ...records }
  for (const item of plan) {
    const existing = next[item.key]
    if (!existing) {
      next[item.key] = {
        key: item.key,
        partUuid: item.part.uuid,
        contentHash: item.part.displayArtifact!.contentHash,
        state: 'queued',
        error: null,
      }
    }
  }
  return next
}

export function nextAssemblyLoadBatch(
  plan: AssemblyLoadPlanItem[],
  records: AssemblyLoadRecords,
  concurrency: number,
): AssemblyLoadPlanItem[] {
  const loading = plan.filter((item) => records[item.key]?.state === 'loading').length
  const available = Math.max(0, Math.floor(concurrency) - loading)
  if (available === 0) return []
  return plan.filter((item) => records[item.key]?.state === 'queued').slice(0, available)
}

export function partLoadStates(
  plan: AssemblyLoadPlanItem[],
  records: AssemblyLoadRecords,
): Record<string, ArtifactState> {
  return Object.fromEntries(plan.map((item) => {
    const state = records[item.key]?.state ?? 'queued'
    return [item.part.uuid, state === 'downloaded' ? 'loading' : state]
  }))
}

export function transformPoint(point: Point3, occurrence: WorkbenchOccurrence): Point3 {
  const [x, y, z] = occurrence.rotationDeg.map((value) => value * Math.PI / 180) as Point3
  const [a, b, c] = [Math.cos(x), Math.sin(x), Math.cos(y)]
  const [d, e, f] = [Math.sin(y), Math.cos(z), Math.sin(z)]
  const [px, py, pz] = point
  return [
    c * e * px - c * f * py + d * pz + occurrence.translationMm[0],
    (a * f + b * d * e) * px + (a * e - b * d * f) * py - b * c * pz + occurrence.translationMm[1],
    (b * f - a * d * e) * px + (b * e + a * d * f) * py + a * c * pz + occurrence.translationMm[2],
  ]
}

export function transformExactFeature(feature: ExactFeature, occurrence: WorkbenchOccurrence): ExactFeature {
  return {
    ...feature,
    pointMm: feature.pointMm ? transformPoint(feature.pointMm, occurrence) : undefined,
    startMm: feature.startMm ? transformPoint(feature.startMm, occurrence) : undefined,
    endMm: feature.endMm ? transformPoint(feature.endMm, occurrence) : undefined,
    midpointMm: feature.midpointMm ? transformPoint(feature.midpointMm, occurrence) : undefined,
  }
}

export function transformBounds(bounds: Bounds3, occurrence: WorkbenchOccurrence): Bounds3 {
  const corners: Point3[] = []
  for (const x of [bounds.min[0], bounds.max[0]]) {
    for (const y of [bounds.min[1], bounds.max[1]]) {
      for (const z of [bounds.min[2], bounds.max[2]]) corners.push(transformPoint([x, y, z], occurrence))
    }
  }
  return corners.reduce<Bounds3>((result, point) => ({
    min: [
      Math.min(result.min[0], point[0]),
      Math.min(result.min[1], point[1]),
      Math.min(result.min[2], point[2]),
    ],
    max: [
      Math.max(result.max[0], point[0]),
      Math.max(result.max[1], point[1]),
      Math.max(result.max[2], point[2]),
    ],
  }), { min: [...corners[0]] as Point3, max: [...corners[0]] as Point3 })
}

export function mergeBounds(bounds: Bounds3[]): Bounds3 | null {
  if (bounds.length === 0) return null
  return bounds.slice(1).reduce<Bounds3>((result, item) => ({
    min: [
      Math.min(result.min[0], item.min[0]),
      Math.min(result.min[1], item.min[1]),
      Math.min(result.min[2], item.min[2]),
    ],
    max: [
      Math.max(result.max[0], item.max[0]),
      Math.max(result.max[1], item.max[1]),
      Math.max(result.max[2], item.max[2]),
    ],
  }), bounds[0])
}

function defaultPriority(part: WorkbenchPart): number {
  if (part.status === 'active') return 10
  if (part.role === 'printable') return 20
  if (part.role === 'inspection') return 30
  return 40
}

function inspectionOccurrence(partUuid: string, assemblyId: string | null): WorkbenchOccurrence {
  return {
    assemblyId: assemblyId ?? 'inspection',
    id: `${partUuid}${IDENTITY_OCCURRENCE_SUFFIX}`,
    translationMm: [0, 0, 0],
    rotationDeg: [0, 0, 0],
  }
}

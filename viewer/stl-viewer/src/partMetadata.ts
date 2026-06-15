import type { PartMetadataDraft, PartMetadataPayload, ViewerPart } from './types'

export type ViewerColorMode = 'workbench' | 'model'

export const WORKBENCH_PART_COLOR = '#8b949e'
export const WORKBENCH_WIREFRAME_COLOR = '#475569'
export const MODEL_WIREFRAME_COLOR = '#1f2937'

const MATERIAL_COLORS: Record<string, string> = {
  petg: '#38bdf8',
  pla: '#f8fafc',
  tpu: '#111827',
  abs: '#f97316',
  nylon: '#e5e7eb',
  aluminum: '#94a3b8',
  steel: '#64748b',
  copper: '#b45309',
  brass: '#ca8a04',
  battery: '#22c55e',
  electronics: '#0f766e',
  rubber: '#111827',
}

const DEFAULT_MODEL_COLOR = '#5ec4ff'

function isHexColor(value: string) {
  return /^#[0-9a-fA-F]{6}$/.test(value.trim())
}

function tupleToStrings(tuple: readonly number[] | null, size: number): string[] {
  if (!tuple) return Array.from({ length: size }, () => '')
  return Array.from({ length: size }, (_, index) => {
    const value = tuple[index]
    return Number.isFinite(value) ? String(value) : ''
  })
}

function parseOptionalNumber(value: string, fallback: number | null): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : fallback
}

function parseOptionalTuple<T extends number>(
  values: readonly string[],
  size: T,
  fallback: readonly number[] | null,
): number[] | null {
  const hasAnyValue = values.some((value) => value.trim() !== '')
  if (!hasAnyValue) return null

  return Array.from({ length: size }, (_, index) => {
    const parsed = Number(values[index] ?? '')
    if (Number.isFinite(parsed)) return parsed
    return fallback?.[index] ?? 0
  })
}

function parseDraftNumber(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

function parseDraftTuple<T extends number>(values: readonly string[], size: T): number[] | null {
  if (!values.some((value) => value.trim() !== '')) return null
  return Array.from({ length: size }, (_, index) => {
    const parsed = Number(values[index] ?? '')
    return Number.isFinite(parsed) ? parsed : 0
  })
}

export function colorForMaterial(material: string) {
  const normalized = material.trim().toLowerCase()
  return MATERIAL_COLORS[normalized] ?? DEFAULT_MODEL_COLOR
}

export function displayColorForPart(part: Pick<ViewerPart, 'material' | 'display_color'>) {
  return part.display_color && isHexColor(part.display_color)
    ? part.display_color
    : colorForMaterial(part.material)
}

export function draftFromPart(part: ViewerPart): PartMetadataDraft {
  return {
    material: part.material,
    display_color: displayColorForPart(part),
    mass_kg: part.mass_kg === null ? '' : String(part.mass_kg),
    mass_source: part.mass_source,
    center_of_mass_mm: tupleToStrings(part.center_of_mass_mm, 3) as [string, string, string],
    inertia_kg_m2: tupleToStrings(part.inertia_kg_m2, 6) as [string, string, string, string, string, string],
  }
}

export function mergePartDraft(part: ViewerPart, draft?: PartMetadataDraft): ViewerPart {
  if (!draft) return { ...part, display_color: displayColorForPart(part) }

  const centerOfMass = parseOptionalTuple(draft.center_of_mass_mm, 3, part.center_of_mass_mm)
  const inertia = parseOptionalTuple(draft.inertia_kg_m2, 6, part.inertia_kg_m2)

  return {
    ...part,
    material: draft.material,
    display_color: draft.display_color || colorForMaterial(draft.material),
    mass_kg: parseOptionalNumber(draft.mass_kg, part.mass_kg),
    center_of_mass_mm: centerOfMass as [number, number, number] | null,
    inertia_kg_m2: inertia as [number, number, number, number, number, number] | null,
    mass_source: draft.mass_source,
  }
}

export function metadataPayloadFromDraft(draft: PartMetadataDraft): PartMetadataPayload {
  return {
    material: draft.material,
    display_color: draft.display_color.trim() ? draft.display_color : null,
    mass_kg: parseDraftNumber(draft.mass_kg),
    center_of_mass_mm: parseDraftTuple(draft.center_of_mass_mm, 3) as [number, number, number] | null,
    inertia_kg_m2: parseDraftTuple(draft.inertia_kg_m2, 6) as [number, number, number, number, number, number] | null,
    mass_source: draft.mass_source,
  }
}

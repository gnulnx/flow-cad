import type { BufferGeometry, Vector3 } from 'three'
import type { MeshMetrics } from './meshMetrics'

export type RotationMode = 'turntable' | 'arcball' | 'free_orbit'
export type SnapFeatureKind = 'vertex' | 'line_edge' | 'edge_midpoint' | 'circle_center' | 'face_point' | 'free_point'

export interface ViewerOccurrence {
  name: string
  assembly_id?: string
  location: [number, number, number]
  rotation: [number, number, number]
}

export interface GeometryCapabilities {
  display_mesh: boolean
  mesh_metrics: boolean
  exact_topology: boolean
  exact_snap: boolean
  exact_measurement: boolean
  approximate_measurement: boolean
  exact_editing: boolean
  mesh_only: boolean
}

export interface ViewerPart {
  id: string
  module_id: string
  version: string
  family: string
  assembly_ids: string[]
  compatible_versions: string[]
  filename: string
  role: string
  material: string
  display_color?: string | null
  mass_kg: number | null
  center_of_mass_mm: [number, number, number] | null
  inertia_kg_m2: [number, number, number, number, number, number] | null
  mass_source: string
  metadata_status: string
  metadata_notes: string
  is_printable: boolean
  artifact_format: 'step' | 'stl' | null
  artifact_path: string | null
  direct_stl_path: string | null
  source_kind: 'flow_python' | 'flow_document' | 'flow_python_with_edits' | 'step' | 'stl' | 'missing'
  geometry_authority: 'step_kernel' | 'mesh' | 'missing'
  quality_label: 'exact' | 'approximate' | 'missing'
  capabilities: GeometryCapabilities
  warnings: string[]
  model_url: string
  source_url: string
  snap_features_url?: string
  occurrences: ViewerOccurrence[]
  in_assembly: boolean
  default_visible: boolean
}

export interface ViewerPartsPayload {
  project_id?: string
  project_name?: string
  revision: number
  active_version?: string | null
  active_assembly_id?: string | null
  versions?: string[]
  parts: ViewerPart[]
}

export interface EditTransform {
  translation_mm: [number, number, number]
  rotation_deg: [number, number, number]
}

export interface EditHoleCut {
  id: string
  point_id: string
  position_mm: [number, number, number]
  axis: [number, number, number]
  preset: string
  diameter_mm: number
  through: boolean
}

export interface EditBooleanOperation {
  id: string
  type: 'fuse' | 'cut'
  tool_entity_id: string
  keep_tool: boolean
}

export interface EditEntity {
  kind: 'primitive_box' | 'derived_split'
  name: string
  size_mm: [number, number, number]
  transform: EditTransform
  role: string
  holes?: EditHoleCut[]
  booleans?: EditBooleanOperation[]
  source_entity_id?: string | null
  split_plane?: {
    origin_mm: [number, number, number]
    normal: [number, number, number]
  }
  split_keep?: 'top' | 'bottom'
}

export interface EditPoint {
  position_mm: [number, number, number]
  coordinate_space: string
  quality: 'exact' | 'approximate'
  source: Record<string, unknown>
}

export interface EditDocumentPayload {
  schema_version: number
  document_id: string
  units: 'mm' | string
  revision: number
  document_path?: string
  entities: Record<string, EditEntity>
  points: Record<string, EditPoint>
  operations: Array<Record<string, unknown>>
}

export interface SnapFeature {
  id: string
  kind: SnapFeatureKind
  label: string
  point?: [number, number, number]
  start?: [number, number, number]
  end?: [number, number, number]
  edge_start?: [number, number, number]
  edge_end?: [number, number, number]
  ring_points?: [number, number, number][]
  length?: number
  radius?: number
  source?: string
  quality?: 'exact' | 'approximate'
  quality_label?: string
}

export interface SnapFeaturePayload {
  component_id: string
  artifact_path: string | null
  source_format: 'step' | 'stl' | null
  features: SnapFeature[]
  warnings: string[]
}

export interface SourceContext {
  component_id: string
  symbol: string
  file_path: string
  relative_file_path: string
  start_line: number
  end_line: number
  highlight_start_line?: number
  highlight_end_line?: number
  language?: string
  content?: string
  excerpt: string
}

export interface ModelData {
  name: string
  partId: string
  geometry: BufferGeometry
  color: string
  wireframeColor: string
  snapFeatures: SnapFeature[]
  sourceKind: ViewerPart['source_kind'] | 'client_stl'
  geometryAuthority: ViewerPart['geometry_authority']
  qualityLabel: ViewerPart['quality_label']
  capabilities: GeometryCapabilities
  warnings: string[]
  occurrences: ViewerOccurrence[]
  bounds: {
    min: Vector3
    max: Vector3
    size: Vector3
    center: Vector3
  }
  metrics: MeshMetrics
}

export interface PartMetadataDraft {
  material: string
  display_color: string
  mass_kg: string
  center_of_mass_mm: [string, string, string]
  inertia_kg_m2: [string, string, string, string, string, string]
  mass_source: string
}

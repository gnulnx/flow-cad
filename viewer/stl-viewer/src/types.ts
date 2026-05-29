import type { BufferGeometry, Vector3 } from 'three'

export type RotationMode = 'turntable' | 'arcball' | 'free_orbit'
export type SnapFeatureKind = 'vertex' | 'line_edge' | 'edge_midpoint' | 'circle_center' | 'face_point' | 'free_point'

export interface ViewerOccurrence {
  name: string
  location: [number, number, number]
  rotation: [number, number, number]
}

export interface ViewerPart {
  id: string
  module_id: string
  filename: string
  role: string
  material: string
  is_printable: boolean
  artifact_format: 'step' | 'stl' | null
  artifact_path: string | null
  direct_stl_path: string | null
  model_url: string
  source_url: string
  snap_features_url?: string
  occurrences: ViewerOccurrence[]
  in_assembly: boolean
  default_visible: boolean
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
  occurrences: ViewerOccurrence[]
  bounds: {
    min: Vector3
    max: Vector3
    size: Vector3
    center: Vector3
  }
}

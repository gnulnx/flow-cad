import type { BufferGeometry, Vector3 } from 'three'

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
  occurrences: ViewerOccurrence[]
  in_assembly: boolean
  default_visible: boolean
}

export interface SourceContext {
  component_id: string
  symbol: string
  file_path: string
  relative_file_path: string
  start_line: number
  end_line: number
  excerpt: string
}

export interface ModelData {
  name: string
  partId: string
  geometry: BufferGeometry
  color: string
  wireframeColor: string
  occurrences: ViewerOccurrence[]
  bounds: {
    min: Vector3
    max: Vector3
    size: Vector3
    center: Vector3
  }
}

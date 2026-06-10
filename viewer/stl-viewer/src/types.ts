import type { BufferGeometry, Vector3 } from 'three'
import type { MeshMetrics } from './meshMetrics'

export type RotationMode = 'turntable' | 'arcball' | 'free_orbit'
export type SnapFeatureKind = 'vertex' | 'line_edge' | 'edge_midpoint' | 'circle_center' | 'face_point' | 'free_point'
export type VisualEvidenceViewPreset = 'front' | 'back' | 'left' | 'right' | 'top' | 'bottom' | 'iso'

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
  source_kind: 'flow_python' | 'step' | 'stl' | 'missing'
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

export interface ImportedModelPayload {
  import_id: string
  part_id: string
  name: string
  filename: string
  source_format: 'step'
  source_kind: 'step'
  geometry_authority: 'step_kernel'
  quality_label: 'exact'
  capabilities: GeometryCapabilities
  warnings: string[]
  model_url: string
  snap_features: SnapFeature[]
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

export interface ThreadViewportMeasurement {
  id: string
  label: string
  distance_mm: number
  quality_label: string
}

export interface ThreadViewportState {
  camera: {
    position: [number, number, number]
    look_direction: [number, number, number]
    up: [number, number, number]
    quaternion: [number, number, number, number]
    fov: number
  }
  viewport: {
    width: number
    height: number
  }
}

export interface ThreadViewportAnnotationNote {
  id?: string
  kind: 'note'
  text: string
  x: number
  y: number
}

export interface ThreadViewportAnnotationCircle {
  id?: string
  kind: 'circle'
  x: number
  y: number
  radius: number
}

export interface ThreadViewportAnnotationFreehand {
  id?: string
  kind: 'freehand'
  points: Array<{ x: number; y: number }>
  color?: string
  width?: number
}

export type ThreadViewportAnnotation =
  | ThreadViewportAnnotationNote
  | ThreadViewportAnnotationCircle
  | ThreadViewportAnnotationFreehand

export type ViewportMarkupTool = 'pen' | 'circle' | 'note'

export interface ViewportScreenshotPayload {
  kind: 'viewport_screenshot'
  content_type: 'image/png'
  data_url?: string
  attachment_id?: string
  selected_part_ids?: string[]
  visible_part_ids?: string[]
  annotations?: ThreadViewportAnnotation[]
  backend_revision?: number | string | null
  viewport?: {
    width: number
    height: number
    client_width?: number
    client_height?: number
  }
  camera?: ThreadViewportState['camera']
}

export interface ViewportAttachmentRecord {
  attachment_id: string
  kind: 'viewport_screenshot'
  content_type: 'image/png'
  filename: string
  path: string
  metadata_path: string
  selected_part_ids: string[]
  visible_part_ids: string[]
  annotations: ThreadViewportAnnotation[]
  created_at: string
}

export interface ThreadVisualEvidenceArtifact {
  artifact_id: string
  source: string
  view: VisualEvidenceViewPreset | string
  content_type: string
  filename?: string
  path: string
  metadata_path?: string
  image_url?: string
  image_endpoint?: string
  width: number | null
  height: number | null
  selected_ids: string[]
  visible_ids: string[]
  part_ids: string[]
  purpose?: string | null
  created_at: string
  metadata?: Record<string, unknown>
}

export type ThreadVisualEvidenceRequestStatus = 'pending' | 'fulfilled' | 'failed' | string

export interface ThreadVisualEvidenceRequest {
  schema_version?: number
  request_id: string
  thread_id?: string
  status: ThreadVisualEvidenceRequestStatus
  source: string
  view: VisualEvidenceViewPreset | string
  width?: number | null
  height?: number | null
  selected_ids: string[]
  visible_ids: string[]
  part_ids: string[]
  purpose?: string | null
  metadata?: Record<string, unknown>
  created_at?: string
  updated_at?: string
  artifact_id?: string | null
  error?: string | null
}

export interface CreateThreadVisualEvidencePayload {
  source: string
  view: VisualEvidenceViewPreset
  content_type: 'image/png'
  data_url: string
  request_id?: string
  width: number | null
  height: number | null
  camera?: Record<string, unknown>
  viewport?: Record<string, unknown>
  selected_ids?: string[]
  visible_ids?: string[]
  part_ids?: string[]
  purpose?: string
  metadata?: Record<string, unknown>
}

export interface ThreadContextSnapshot {
  schema_version?: number
  thread_id?: string
  snapshot_id: string
  created_at?: string
  selected_part_ids: string[]
  visible_part_ids: string[]
  measurements?: ThreadViewportMeasurement[]
  warnings?: string[]
  project?: Record<string, unknown>
  parts?: Record<string, unknown>
  viewport?: Record<string, unknown>
  camera?: Record<string, unknown> | null
  draft_transaction?: {
    token: string
    status?: string
    error?: string
  } | null
  draft_transaction_token?: string | null
  draft_preview_token?: string | null
  draft_preview_model_url?: string | null
  draft_preview_available?: boolean
  active_assembly_id?: string | null
  camera_state?: ThreadViewportState
  active_project_revision?: number | null
  context_note?: string
  viewer_state?: {
    viewport_screenshot?: ViewportScreenshotPayload
    [key: string]: unknown
  }
}

export type DesignThreadEventType =
  | 'user_message'
  | 'assistant_message'
  | 'tool_call'
  | 'tool_result'
  | 'context_snapshot'
  | 'draft_event'
  | 'design_plan'
  | 'review_event'
  | 'status'
  | 'system'

export interface DesignThreadMessagePayload {
  type: DesignThreadEventType
  role: 'user' | 'assistant' | 'system'
  content: string | Record<string, unknown>
  attachments?: string[]
  metadata?: Record<string, unknown>
}

export type DraftThreadAction = 'propose' | 'apply' | 'preview' | 'accept' | 'discard' | 'reset'

export interface DesignThreadDraftEventPayload {
  type: 'draft_event'
  role: 'assistant' | 'system'
  content: string | Record<string, unknown>
  metadata?: Record<string, unknown>
  action?: DraftThreadAction
  summary?: string
}

export interface DesignThreadDraftEventRequest {
  message_id: string
  thread_id: string
  created_at: string
  type: 'draft_event'
  role: 'assistant' | 'system'
  content: string | Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface DesignThreadDraftEventResponse {
  thread?: DesignThreadRecord
  messages?: DesignThreadEvent[]
  message?: DesignThreadEvent
}

export interface DesignThreadToolCallPayload {
  kind: 'tool_call'
  tool: string
  summary: string
  inputs?: unknown
}

export interface DesignThreadToolResultPayload {
  kind: 'tool_result'
  tool: string
  status: 'success' | 'error'
  summary: string
  details?: Record<string, unknown>
}

export interface DesignThreadEvent {
  schema_version?: number
  message_id: string
  thread_id: string
  created_at?: string
  type: DesignThreadEventType
  role?: 'user' | 'assistant' | 'system'
  content: string | Record<string, unknown>
  attachments?: string[]
  metadata?: Record<string, unknown>
}

export interface DesignThreadRecord {
  thread_id: string
  schema_version?: number
  title: string
  status: string
  archived?: boolean
  created_at: string
  updated_at: string
  project_id?: string
  project_name?: string
  active_version?: string | null
  active_assembly_id?: string | null
  active_part_id?: string | null
  summary?: string
  tags?: string[]
  linked_part_ids?: string[]
  linked_draft_transaction_tokens?: string[]
  accepted_artifact_paths?: string[]
  warnings?: string[]
  message_count?: number
  snapshot_count?: number
  attachment_count?: number
  visual_evidence_count?: number
  visual_evidence?: ThreadVisualEvidenceArtifact[]
  visual_evidence_request_count?: number
  visual_evidence_requests?: ThreadVisualEvidenceRequest[]
  messages: DesignThreadEvent[]
  context_snapshots?: ThreadContextSnapshot[]
  attachments?: ViewportAttachmentRecord[]
}

export interface DesignThreadSummary {
  thread_id: string
  title: string
  status: string
  archived?: boolean
  created_at?: string
  updated_at: string
  message_count?: number
  active_part_id?: string | null
}

export interface DesignThreadsPayload {
  threads: DesignThreadSummary[]
}

export interface CreateDesignThreadPayload {
  title?: string
  thread_id?: string
  summary?: string
  tags?: string[]
  linked_part_ids?: string[]
  linked_draft_transaction_tokens?: string[]
  accepted_artifact_paths?: string[]
}

export interface DesignThreadChatPayload {
  message: string
  context_snapshot?: Record<string, unknown>
  attachments?: string[]
  metadata?: Record<string, unknown>
}

export interface DesignThreadChatResponse {
  thread_id: string
  messages: DesignThreadEvent[]
  context_snapshot?: ThreadContextSnapshot | null
  thread: DesignThreadRecord
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

export interface PreviewContext {
  component_id: string
  module_id: string
  family: string
  version: string
  role: string
  material: string
  artifact_format: 'step' | 'stl' | null
  artifact_path: string | null
  source_context_available: boolean
  source_url: string | null
  occurrences: ViewerOccurrence[]
  geometry_authority: 'step_kernel' | 'mesh' | 'missing'
  quality_label: 'exact' | 'approximate' | 'missing'
  capabilities: GeometryCapabilities
  warnings: string[]
  source_measurements: MeasurementSummary | null
  active_assembly_id?: string | null
  project_frame?: FrameSummary
  local_frame?: FrameSummary
  mating_contracts?: MatingContractSummary
}

export interface MeasurementSummary {
  length_mm: number
  width_mm: number
  height_mm: number
  authority: 'step_kernel' | 'mesh' | 'missing'
  source: 'part' | 'preview'
}

export interface FrameSummary {
  units: string
  origin_mm: [number, number, number]
  rotation_deg?: [number, number, number]
  axes: Record<string, string>
}

export interface MatingContractSummary {
  available: boolean
  relative_path: string
  summary: string
}

export interface ProposedPreviewOperation {
  kind: 'box' | 'hole' | 'louver-patterns' | 'thickness' | 'unknown'
  summary: string
  payload: Record<string, unknown>
  endpoint: 'box' | 'holes' | 'louver-patterns' | 'thickness'
}

export interface BackendPreviewOperation {
  name: 'create_box' | 'add_hole' | 'add_louver_pattern' | 'set_panel_thickness' | string
  parameters: Record<string, unknown>
}

export interface PreviewCommandProposal {
  command: string
  ok: boolean
  operations: BackendPreviewOperation[]
  warnings: string[]
  assumptions: string[]
  errors: string[]
  part_id?: string | null
}

export interface DraftPreviewSession {
  transaction_token: string | null
  proposed_operations: ProposedPreviewOperation[]
  preview_model: DraftPreviewModelPayload | null
  acceptance_artifacts: DraftAcceptanceArtifacts | null
}

export interface DraftPreviewModelPayload {
  transaction_token: string
  part_id: string
  model_url: string
  preview_step_path?: string | null
  preview_step_relative_path?: string | null
  display_stl_path: string | null
  display_stl_relative_path?: string | null
  source_step_path: string | null
  source_format?: string
  geometry_authority: 'step_kernel' | 'mesh' | 'missing'
  quality_label: 'exact' | 'approximate' | 'missing'
  facts: string[]
  warnings: string[]
  dimensions: MeasurementSummary | null
}

export interface DraftAcceptanceArtifacts {
  transaction_token: string
  source_patch_path: string
  source_patch_relative_path?: string
  generated_source_path: string
  generated_source_relative_path?: string
  validator_stub_path: string
  validator_stub_relative_path?: string
  acceptance_manifest_path: string
  acceptance_manifest_relative_path?: string
  source_loop_commands?: string[]
  source_patch_preview?: string
  command_source?: string
}

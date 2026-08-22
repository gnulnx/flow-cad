export type ArtifactState =
  | 'indexed'
  | 'queued'
  | 'loading'
  | 'visible'
  | 'stale'
  | 'missing'
  | 'failed'

export type GeometryAuthority = 'step' | 'mesh' | 'missing'

export interface Bounds3 {
  min: [number, number, number]
  max: [number, number, number]
}

export interface DisplayArtifact {
  contentHash: string
  format: 'stl'
  url: string
  revision: number
}

export interface WorkbenchOccurrence {
  assemblyId: string
  id: string
  translationMm: Point3
  rotationDeg: Point3
}

export interface WorkbenchPart {
  uuid: string
  key: string
  aliases: string[]
  role: 'printable' | 'reference' | 'inspection' | 'legacy'
  status: 'preserved-only' | 'active' | 'reference' | 'inspection' | 'retired' | 'superseded'
  artifactState: ArtifactState
  geometryAuthority: GeometryAuthority
  qualityLabel: 'Exact' | 'Approximate' | 'Missing'
  occurrenceCount: number
  occurrenceIds: string[]
  occurrences: WorkbenchOccurrence[]
  authorityHash: string | null
  displayArtifact: DisplayArtifact | null
  bounds: Bounds3 | null
  warnings: string[]
}

export interface ProjectSummary {
  projectId: string
  projectName: string
  revision: number
  activeAssemblyId: string | null
  gitCommit: string | null
  gitDirty: boolean
  chatAvailable: boolean
}

export interface InventorySnapshot {
  revision: number
  activeAssemblyId: string | null
  parts: WorkbenchPart[]
}

export type ExactFeatureKind = 'vertex' | 'line_edge' | 'edge_midpoint' | 'circle_center'
export type Point3 = [number, number, number]

export interface ExactFeature {
  id: string
  kind: ExactFeatureKind
  quality: 'exact'
  source: 'step_topology'
  pointMm?: Point3
  startMm?: Point3
  endMm?: Point3
  midpointMm?: Point3
  lengthMm?: number
  radiusMm?: number
  edgeLengthMm?: number
  edgeFeatureId?: string
}

export interface ExactFeatureSet {
  status: 'ready'
  partUuid: string
  artifactRevision: string
  geometryAuthority: 'step_kernel'
  quality: 'exact'
  units: 'mm'
  features: ExactFeature[]
  warnings: string[]
  cacheHit: boolean
}

export interface ExactFeatureJobRequired {
  status: 'job_required'
  partUuid: string
  artifactRevision: string
  geometryAuthority: 'step_kernel'
  quality: 'exact'
}

export interface ExactFeatureJobQueued {
  status: 'queued' | 'running'
  partUuid: string
  artifactRevision: string
  jobId: string
  resultUrl: string
}

export type ExactFeatureLookup = ExactFeatureSet | ExactFeatureJobRequired
export type ExactFeatureSubmission = ExactFeatureSet | ExactFeatureJobQueued

export type JobState = 'queued' | 'running' | 'complete' | 'failed' | 'cancelled'

export interface WorkbenchJob {
  id: string
  label: string
  state: JobState
  phase: string
  progress: number | null
  cancellable: boolean
  elapsedMs: number
  lastUpdate: string
}

export interface ThreadSummary {
  id: string
  title: string
  status: 'ready' | 'running' | 'failed'
}

export interface ThreadMessage {
  id: string
  turnId?: string | null
  role: 'user' | 'assistant'
  content: string
  state: 'complete' | 'streaming' | 'failed'
}

export interface DefaultThread {
  thread: ThreadSummary
  messages: ThreadMessage[]
}

export interface ChatContext {
  projectRevision: number | null
  selectedPartUuid: string | null
  selectedPartKey: string | null
  visibleOccurrenceIds: string[]
  artifactHashes: Record<string, string>
}

export interface SendTurnInput {
  requestId: string
  threadId: string
  content: string
  context: ChatContext
}

export interface SavedMeasurementLabel {
  measurementId: string
  kind: 'distance' | 'edge_length'
  title: string
  quality: 'exact' | 'approximate'
  startMm: Point3
  endMm: Point3
  totalMm: number
  deltaMm: Point3
  featureIds: string[]
  hidden: boolean
  pinned: boolean
  labelOffsetPx: [number, number]
}

export interface SavedMeasurementSnapshot {
  threadId: string
  partUuid: string
  artifactRevision: string
  measurements: SavedMeasurementLabel[]
}

export interface SaveMeasurementSnapshotInput extends SavedMeasurementSnapshot {
  requestId: string
}

export interface WorkbenchClient {
  getProject(signal?: AbortSignal): Promise<ProjectSummary>
  getInventory(signal?: AbortSignal): Promise<InventorySnapshot>
  getJobs(signal?: AbortSignal): Promise<WorkbenchJob[]>
  getDefaultThread(signal?: AbortSignal): Promise<DefaultThread>
  sendTurn(input: SendTurnInput, signal?: AbortSignal): Promise<ThreadMessage>
  cancelTurn(threadId: string, turnId: string): Promise<void>
  cancelJob(jobId: string): Promise<void>
  getExactFeatures(partUuid: string, artifactRevision: string, signal?: AbortSignal): Promise<ExactFeatureLookup>
  queueExactFeatures(partUuid: string, artifactRevision: string, requestId: string, signal?: AbortSignal): Promise<ExactFeatureSubmission>
  getLatestMeasurementSnapshot(threadId: string, partUuid: string, signal?: AbortSignal): Promise<SavedMeasurementSnapshot | null>
  saveMeasurementSnapshot(input: SaveMeasurementSnapshotInput, signal?: AbortSignal): Promise<void>
}

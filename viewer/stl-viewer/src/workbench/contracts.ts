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
  parts: WorkbenchPart[]
}

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

export interface WorkbenchClient {
  getProject(signal?: AbortSignal): Promise<ProjectSummary>
  getInventory(signal?: AbortSignal): Promise<InventorySnapshot>
  getJobs(signal?: AbortSignal): Promise<WorkbenchJob[]>
  getDefaultThread(signal?: AbortSignal): Promise<DefaultThread>
  sendTurn(input: SendTurnInput, signal?: AbortSignal): Promise<ThreadMessage>
  cancelTurn(threadId: string, turnId: string): Promise<void>
  cancelJob(jobId: string): Promise<void>
}

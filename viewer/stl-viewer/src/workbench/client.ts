import type {
  ExactFeature,
  ExactFeatureLookup,
  ExactFeatureSet,
  ExactFeatureSubmission,
  InventorySnapshot,
  ProjectSummary,
  SendTurnInput,
  ThreadMessage,
  WorkbenchClient,
  WorkbenchJob,
} from './contracts'

declare global {
  interface Window {
    __FLOW_CAD_WORKBENCH_CLIENT__?: WorkbenchClient
  }
}

const API_ROOT = (import.meta.env.VITE_FLOW_CAD_API as string | undefined)?.replace(/\/$/, '') ?? ''
const CONTRACT_ROOT = '/api/workbench/v1'

export function applicationApiUrl(path: string) {
  return `${API_ROOT}${path.startsWith('/') ? path : `/${path}`}`
}

interface ProjectDto {
  project_id: string
  python_package: string
  manifest_schema_version: number
  manifest_sha256: string
  revision: number
  part_count: number
  occurrence_count: number
}

interface PartDto {
  uuid: string
  key: string
  aliases: string[]
  role: 'printable' | 'reference' | 'inspection' | 'legacy'
  status: string
  artifacts: Array<{
    kind: string
    sha256: string | null
    state: string
  }>
  occurrences: Array<{ id: string }>
  geometry_authority: string
  quality_label: string
  capabilities: {
    exact_topology: boolean
    mesh_only: boolean
  }
  warnings: string[]
  artifact_revision: string | null
  display_revision: string | null
  model_url: string | null
}

interface InventoryDto extends ProjectDto {
  parts: PartDto[]
}

interface ChatEventDto {
  event_id: string
  turn_id: string | null
  event_type: string
  payload: Record<string, unknown>
}

interface ThreadDto {
  thread_id: string
  title: string
  events: ChatEventDto[]
}

interface BeginTurnDto {
  turn_id: string
  events: ChatEventDto[]
  provider_status: string
}

interface JobDto {
  job_id: string
  kind: string
  state: string
  phase: string
  progress: number | null
  message: string
  elapsed_seconds: number
  updated_at: string
  cancellation_requested: boolean
  payload?: Record<string, unknown>
}

interface ExactFeatureDto {
  id: string
  kind: ExactFeature['kind']
  quality: 'exact'
  source: 'step_topology'
  point_mm?: [number, number, number]
  start_mm?: [number, number, number]
  end_mm?: [number, number, number]
  midpoint_mm?: [number, number, number]
  length_mm?: number
  radius_mm?: number
  edge_length_mm?: number
  edge_feature_id?: string
}

interface ExactFeatureSetDto {
  status: 'ready'
  part_uuid: string
  artifact_revision: string
  geometry_authority: 'step_kernel'
  quality: 'exact'
  units: 'mm'
  features: ExactFeatureDto[]
  warnings: string[]
  cache_hit?: boolean
}

interface ExactFeatureRequiredDto {
  status: 'job_required'
  part_uuid: string
  artifact_revision: string
  geometry_authority: 'step_kernel'
  quality: 'exact'
}

interface ExactFeatureQueuedDto {
  status: 'queued' | 'running'
  part_uuid: string
  artifact_revision: string
  job: { job_id: string }
  result_url: string
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

function threadMessages(events: ChatEventDto[]): ThreadMessage[] {
  const messages: ThreadMessage[] = []
  const assistantByTurn = new Map<string, ThreadMessage>()
  events.forEach((event) => {
    if (event.event_type === 'user_message') {
      messages.push({
        id: event.event_id,
        turnId: event.turn_id,
        role: 'user',
        content: String(event.payload.content ?? ''),
        state: 'complete',
      })
      return
    }
    if (!event.turn_id || !event.event_type.startsWith('assistant_')) return
    let assistant = assistantByTurn.get(event.turn_id)
    if (!assistant) {
      assistant = {
        id: event.event_id,
        turnId: event.turn_id,
        role: 'assistant',
        content: '',
        state: 'streaming',
      }
      assistantByTurn.set(event.turn_id, assistant)
      messages.push(assistant)
    }
    if (event.event_type === 'assistant_delta') assistant.content += String(event.payload.content ?? event.payload.delta ?? '')
    if (event.event_type === 'assistant_progress') assistant.content = String(event.payload.summary ?? event.payload.message ?? assistant.content)
    if (event.event_type === 'assistant_completed') {
      assistant.content = String(event.payload.content ?? assistant.content)
      assistant.state = 'complete'
    }
    if (event.event_type === 'assistant_failed') {
      assistant.content = String(event.payload.error ?? event.payload.message ?? 'Agent request failed')
      assistant.state = 'failed'
    }
  })
  return messages.map((message) => message.role === 'assistant' && !message.content
    ? { ...message, content: 'Queued for agent dispatch…' }
    : message)
}

function jobRecords(payload: JobDto[] | { jobs: JobDto[] }): WorkbenchJob[] {
  const records = Array.isArray(payload) ? payload : payload.jobs
  return records.map((job) => ({
    id: job.job_id,
    label: String(job.payload?.label ?? job.kind),
    state: job.state === 'succeeded'
      ? 'complete'
      : ['queued', 'running', 'complete', 'failed', 'cancelled'].includes(job.state)
        ? job.state as WorkbenchJob['state']
        : 'failed',
    phase: job.phase,
    progress: job.progress,
    cancellable: !job.cancellation_requested && (job.state === 'queued' || job.state === 'running'),
    elapsedMs: job.elapsed_seconds * 1000,
    lastUpdate: job.updated_at,
  }))
}

function exactFeatureSet(dto: ExactFeatureSetDto): ExactFeatureSet {
  return {
    status: 'ready',
    partUuid: dto.part_uuid,
    artifactRevision: dto.artifact_revision,
    geometryAuthority: dto.geometry_authority,
    quality: dto.quality,
    units: dto.units,
    features: dto.features.map((feature) => ({
      id: feature.id,
      kind: feature.kind,
      quality: feature.quality,
      source: feature.source,
      pointMm: feature.point_mm,
      startMm: feature.start_mm,
      endMm: feature.end_mm,
      midpointMm: feature.midpoint_mm,
      lengthMm: feature.length_mm,
      radiusMm: feature.radius_mm,
      edgeLengthMm: feature.edge_length_mm,
      edgeFeatureId: feature.edge_feature_id,
    })),
    warnings: dto.warnings,
    cacheHit: dto.cache_hit ?? false,
  }
}

async function readExactLookup(response: Response): Promise<ExactFeatureLookup> {
  const dto = await readJson<ExactFeatureSetDto | ExactFeatureRequiredDto>(response)
  if (dto.status === 'ready') return exactFeatureSet(dto)
  return {
    status: 'job_required',
    partUuid: dto.part_uuid,
    artifactRevision: dto.artifact_revision,
    geometryAuthority: dto.geometry_authority,
    quality: dto.quality,
  }
}

async function readExactSubmission(response: Response): Promise<ExactFeatureSubmission> {
  const dto = await readJson<ExactFeatureSetDto | ExactFeatureQueuedDto>(response)
  if (dto.status === 'ready') return exactFeatureSet(dto)
  return {
    status: dto.status,
    partUuid: dto.part_uuid,
    artifactRevision: dto.artifact_revision,
    jobId: dto.job.job_id,
    resultUrl: dto.result_url,
  }
}

export function createHttpWorkbenchClient(baseUrl = `${API_ROOT}${CONTRACT_ROOT}`): WorkbenchClient {
  const applicationUrl = API_ROOT
  const projectSummary = (dto: ProjectDto): ProjectSummary => ({
    projectId: dto.project_id,
    projectName: dto.project_id,
    revision: dto.revision,
    activeAssemblyId: null,
    gitCommit: null,
    gitDirty: false,
    chatAvailable: true,
  })
  const inventorySnapshot = (dto: InventoryDto): InventorySnapshot => ({
    revision: dto.revision,
    parts: dto.parts.map((part) => {
      const displayArtifact = part.artifacts.find((artifact) => artifact.kind.toLocaleLowerCase() === 'stl')
      const rawState = displayArtifact?.state ?? (part.model_url ? 'indexed' : 'missing')
      const artifactState = ['indexed', 'queued', 'loading', 'visible', 'stale', 'missing', 'failed'].includes(rawState)
        ? rawState as InventorySnapshot['parts'][number]['artifactState']
        : rawState === 'available' || rawState === 'ready' ? 'indexed' : 'missing'
      const status = ['preserved-only', 'active', 'reference', 'inspection', 'retired', 'superseded'].includes(part.status)
        ? part.status as InventorySnapshot['parts'][number]['status']
        : 'preserved-only'
      const geometryAuthority = part.capabilities.exact_topology
        ? 'step'
        : part.capabilities.mesh_only ? 'mesh' : 'missing'
      const qualityLabel = geometryAuthority === 'step' ? 'Exact' : geometryAuthority === 'mesh' ? 'Approximate' : 'Missing'
      return {
        uuid: part.uuid,
        key: part.key,
        aliases: part.aliases,
        role: part.role,
        status,
        artifactState,
        geometryAuthority,
        qualityLabel,
        occurrenceCount: part.occurrences.length,
        occurrenceIds: part.occurrences.map((occurrence) => occurrence.id),
        authorityHash: part.artifact_revision,
        displayArtifact: part.model_url && part.display_revision
          ? {
              contentHash: part.display_revision,
              format: 'stl',
              url: part.model_url.startsWith('http') ? part.model_url : `${API_ROOT}${part.model_url}`,
              revision: dto.revision,
            }
          : null,
        bounds: null,
        warnings: part.warnings,
      }
    }),
  })
  return {
    getProject: (signal) => fetch(`${applicationUrl}/api/project`, { signal }).then(readJson<ProjectDto>).then(projectSummary),
    getInventory: (signal) => fetch(`${applicationUrl}/api/parts`, { signal }).then(readJson<InventoryDto>).then(inventorySnapshot),
    getJobs: (signal) => fetch(`${baseUrl}/jobs`, { signal }).then(readJson<JobDto[] | { jobs: JobDto[] }>).then(jobRecords),
    getDefaultThread: (signal) => fetch(`${applicationUrl}/api/chat/threads/default`, { signal })
      .then(readJson<ThreadDto>)
      .then((dto) => ({
        thread: { id: dto.thread_id, title: dto.title, status: 'ready' },
        messages: threadMessages(dto.events),
      })),
    sendTurn: (input: SendTurnInput, signal) => fetch(`${applicationUrl}/api/chat/threads/${encodeURIComponent(input.threadId)}/turns`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: input.requestId,
        content: input.content,
        context: {
          selected_part_uuid: input.context.selectedPartUuid,
          visible_occurrence_ids: input.context.visibleOccurrenceIds,
          artifact_hashes: input.context.artifactHashes,
          viewer_revision: input.context.projectRevision === null ? null : String(input.context.projectRevision),
        },
      }),
      signal,
    }).then(readJson<BeginTurnDto>).then((dto) => ({
      id: dto.events.find((event) => event.event_type === 'assistant_created')?.event_id ?? `${input.requestId}-assistant`,
      turnId: dto.turn_id,
      role: 'assistant',
      content: dto.provider_status === 'awaiting_dispatch' ? 'Queued for agent dispatch…' : 'Agent is working…',
      state: 'streaming',
    })),
    cancelTurn: (threadId, turnId) => fetch(`${applicationUrl}/api/chat/threads/${encodeURIComponent(threadId)}/turns/${encodeURIComponent(turnId)}/cancel`, {
      method: 'POST',
    }).then(async (response) => {
      if (!response.ok) throw new Error(await response.text())
    }),
    cancelJob: (jobId) => fetch(`${baseUrl}/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    }).then(async (response) => {
      if (!response.ok) throw new Error(await response.text())
    }),
    getExactFeatures: (partUuid, artifactRevision, signal) => fetch(
      `${applicationUrl}/api/parts/${encodeURIComponent(partUuid)}/exact-features?artifact_revision=${encodeURIComponent(artifactRevision)}`,
      { signal, cache: 'no-store' },
    ).then(readExactLookup),
    queueExactFeatures: (partUuid, artifactRevision, requestId, signal) => fetch(
      `${applicationUrl}/api/parts/${encodeURIComponent(partUuid)}/exact-features/jobs`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, artifact_revision: artifactRevision }),
        signal,
      },
    ).then(readExactSubmission),
  }
}

export function configuredWorkbenchClient(): WorkbenchClient {
  return window.__FLOW_CAD_WORKBENCH_CLIENT__ ?? createHttpWorkbenchClient()
}

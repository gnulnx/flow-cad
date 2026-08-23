import type {
  ExactFeature,
  ExactFeatureLookup,
  ExactFeatureSet,
  ExactFeatureSubmission,
  ChatProviderStatus,
  ChatTurnEvent,
  InventorySnapshot,
  ProjectSummary,
  SavedMeasurementSnapshot,
  SaveMeasurementSnapshotInput,
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
  view_state_revision?: string | null
  part_count: number
  occurrence_count: number
  active_assembly_id?: string | null
}

interface PartDto {
  uuid: string
  key: string
  aliases: string[]
  family?: string | null
  material?: string | null
  role: 'printable' | 'reference' | 'inspection' | 'legacy'
  status: string
  artifacts: Array<{
    kind: string
    sha256: string | null
    state: string
  }>
  occurrences: Array<{
    assembly_key: string
    id: string
    translation_mm: [number, number, number]
    rotation_deg: [number, number, number]
  }>
  preview_of_uuid?: string | null
  preview_replaced_by_uuid?: string | null
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
  sequence: number
  event_id: string
  turn_id: string | null
  event_type: string
  payload: Record<string, unknown>
}

interface ChatProviderDto {
  provider: string | null
  available: boolean
  status: string
  diagnostics?: {
    executable_available?: boolean
    authenticated?: boolean
    auth_method?: string | null
    last_failure_reason?: string | null
    last_rpc_method?: string | null
  }
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

interface BuildSubmissionDto {
  created: boolean
  job: JobDto
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

interface MeasurementLabelDto {
  measurement_id: string
  kind: 'distance' | 'edge_length'
  title: string
  quality: 'exact' | 'approximate'
  start_mm: [number, number, number]
  end_mm: [number, number, number]
  total_mm: number
  delta_mm: [number, number, number]
  feature_ids: string[]
  hidden: boolean
  pinned: boolean
  label_offset_px: [number, number]
}

interface MeasurementSnapshotDto {
  snapshot: {
    thread_id: string
    part_uuid: string
    artifact_revision: string
    measurements: MeasurementLabelDto[]
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

function chatTurnEvent(event: ChatEventDto): ChatTurnEvent {
  return {
    sequence: event.sequence,
    eventId: event.event_id,
    turnId: event.turn_id,
    eventType: event.event_type,
    payload: event.payload,
  }
}

export function applyChatTurnEvent(message: ThreadMessage, event: ChatTurnEvent): ThreadMessage {
  if (event.turnId && message.turnId && event.turnId !== message.turnId) return message
  if (event.eventType === 'assistant_delta') {
    return {
      ...message,
      afterSequence: event.sequence,
      content: message.content === 'Agent is working…' || message.content === 'Queued for agent dispatch…'
        ? String(event.payload.content ?? event.payload.delta ?? '')
        : message.content + String(event.payload.content ?? event.payload.delta ?? ''),
    }
  }
  if (event.eventType === 'assistant_progress') {
    const activity = String(event.payload.content ?? event.payload.summary ?? event.payload.message ?? '').trim()
    return {
      ...message,
      afterSequence: event.sequence,
      activity: activity ? [...(message.activity ?? []), activity].slice(-8) : message.activity,
    }
  }
  if (event.eventType === 'assistant_evidence') {
    return {
      ...message,
      afterSequence: event.sequence,
      evidence: [...(message.evidence ?? []), event.payload],
    }
  }
  if (event.eventType === 'assistant_completed') {
    return {
      ...message,
      afterSequence: event.sequence,
      content: String(event.payload.content ?? message.content),
      state: 'complete',
    }
  }
  if (event.eventType === 'assistant_failed' || event.eventType === 'turn_cancelled') {
    return {
      ...message,
      afterSequence: event.sequence,
      content: event.eventType === 'turn_cancelled'
        ? 'Cancelled.'
        : String(event.payload.error ?? event.payload.message ?? 'Agent request failed'),
      state: 'failed',
    }
  }
  return { ...message, afterSequence: event.sequence }
}

function threadMessages(events: ChatEventDto[]): ThreadMessage[] {
  const messages: ThreadMessage[] = []
  const assistantByTurn = new Map<string, ThreadMessage>()
  events.forEach((event) => {
    if (event.event_type === 'user_message') {
      messages.push({
        id: event.event_id,
        turnId: event.turn_id,
        afterSequence: event.sequence,
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
        afterSequence: event.sequence,
        role: 'assistant',
        content: '',
        state: 'streaming',
      }
      assistantByTurn.set(event.turn_id, assistant)
      messages.push(assistant)
    }
    Object.assign(assistant, applyChatTurnEvent(assistant, chatTurnEvent(event)))
  })
  return messages.map((message) => message.role === 'assistant' && !message.content
    ? { ...message, content: 'Queued for agent dispatch…' }
    : message)
}

async function streamSse(
  response: Response,
  onEvent: (event: ChatTurnEvent) => void,
) {
  if (!response.ok) throw new Error(await response.text() || `${response.status} ${response.statusText}`)
  if (!response.body) throw new Error('Chat event stream is unavailable')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffered = ''
  while (true) {
    const { value, done } = await reader.read()
    buffered += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    if (done && buffered.trim()) buffered += '\n\n'
    let boundary = buffered.indexOf('\n\n')
    while (boundary >= 0) {
      const frame = buffered.slice(0, boundary)
      buffered = buffered.slice(boundary + 2)
      const data = frame.split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (data) onEvent(chatTurnEvent(JSON.parse(data) as ChatEventDto))
      boundary = buffered.indexOf('\n\n')
    }
    if (done) break
  }
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

function measurementSnapshot(dto: MeasurementSnapshotDto): SavedMeasurementSnapshot {
  return {
    threadId: dto.snapshot.thread_id,
    partUuid: dto.snapshot.part_uuid,
    artifactRevision: dto.snapshot.artifact_revision,
    measurements: dto.snapshot.measurements.map((measurement) => ({
      measurementId: measurement.measurement_id,
      kind: measurement.kind,
      title: measurement.title,
      quality: measurement.quality,
      startMm: measurement.start_mm,
      endMm: measurement.end_mm,
      totalMm: measurement.total_mm,
      deltaMm: measurement.delta_mm,
      featureIds: measurement.feature_ids,
      hidden: measurement.hidden,
      pinned: measurement.pinned,
      labelOffsetPx: measurement.label_offset_px,
    })),
  }
}

function saveMeasurementBody(input: SaveMeasurementSnapshotInput) {
  return {
    request_id: input.requestId,
    artifact_revision: input.artifactRevision,
    measurements: input.measurements.map((measurement) => ({
      measurement_id: measurement.measurementId,
      kind: measurement.kind,
      title: measurement.title,
      quality: measurement.quality,
      start_mm: measurement.startMm,
      end_mm: measurement.endMm,
      total_mm: measurement.totalMm,
      delta_mm: measurement.deltaMm,
      feature_ids: measurement.featureIds,
      hidden: measurement.hidden,
      pinned: measurement.pinned,
      label_offset_px: measurement.labelOffsetPx,
    })),
  }
}

export function createHttpWorkbenchClient(baseUrl = `${API_ROOT}${CONTRACT_ROOT}`): WorkbenchClient {
  const applicationUrl = API_ROOT
  const projectSummary = (dto: ProjectDto): ProjectSummary => ({
    projectId: dto.project_id,
    projectName: dto.project_id,
    revision: dto.revision,
    viewStateRevision: dto.view_state_revision ?? null,
    activeAssemblyId: dto.active_assembly_id ?? null,
    gitCommit: null,
    gitDirty: false,
    chatAvailable: true,
  })
  const inventorySnapshot = (dto: InventoryDto): InventorySnapshot => {
    const assemblyIds = dto.parts.flatMap((part) => part.occurrences.map((occurrence) => occurrence.assembly_key))
    const activeAssemblyId = dto.active_assembly_id
      ?? (assemblyIds.includes('active') ? 'active' : assemblyIds[0] ?? null)
    return {
      revision: dto.revision,
      activeAssemblyId,
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
        family: part.family ?? null,
        material: part.material ?? null,
        role: part.role,
        status,
        artifactState,
        geometryAuthority,
        qualityLabel,
        occurrenceCount: part.occurrences.length,
        occurrenceIds: part.occurrences.map((occurrence) => occurrence.id),
        occurrences: part.occurrences.map((occurrence) => ({
          assemblyId: occurrence.assembly_key,
          id: occurrence.id,
          translationMm: occurrence.translation_mm,
          rotationDeg: occurrence.rotation_deg,
        })),
        previewOfUuid: part.preview_of_uuid ?? null,
        previewReplacedByUuid: part.preview_replaced_by_uuid ?? null,
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
    }
  }
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
    getChatProvider: (signal) => fetch(`${applicationUrl}/api/chat/provider`, { signal })
      .then(readJson<ChatProviderDto>)
      .then((dto): ChatProviderStatus => ({
        provider: dto.provider,
        available: dto.available,
        status: ['ready', 'busy', 'unavailable', 'stopping'].includes(dto.status)
          ? dto.status as ChatProviderStatus['status']
          : 'unavailable',
        diagnostics: dto.diagnostics ? {
          executableAvailable: dto.diagnostics.executable_available ?? null,
          authenticated: dto.diagnostics.authenticated ?? null,
          authMethod: dto.diagnostics.auth_method ?? null,
          lastFailureReason: dto.diagnostics.last_failure_reason ?? null,
          lastRpcMethod: dto.diagnostics.last_rpc_method ?? null,
        } : undefined,
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
          camera: input.context.camera,
          measurements: input.context.measurements,
          annotations: input.context.annotations,
          viewport_attachment: input.context.viewportAttachment,
          viewer_revision: input.context.projectRevision === null ? null : String(input.context.projectRevision),
        },
      }),
      signal,
    }).then(readJson<BeginTurnDto>).then((dto) => ({
      id: dto.events.find((event) => event.event_type === 'assistant_created')?.event_id ?? `${input.requestId}-assistant`,
      turnId: dto.turn_id,
      afterSequence: Math.max(...dto.events.map((event) => event.sequence), 0),
      role: 'assistant',
      content: dto.provider_status === 'awaiting_dispatch' ? 'Queued for agent dispatch…' : 'Agent is working…',
      state: 'streaming',
    })),
    streamTurn: (threadId, turnId, afterSequence, onEvent, signal) => fetch(
      `${applicationUrl}/api/chat/threads/${encodeURIComponent(threadId)}/turns/${encodeURIComponent(turnId)}/stream?after_sequence=${afterSequence}`,
      { signal, cache: 'no-store', headers: { Accept: 'text/event-stream' } },
    ).then((response) => streamSse(response, onEvent)),
    buildPart: (partIdentity, requestId, signal) => fetch(
      `${baseUrl}/parts/${encodeURIComponent(partIdentity)}/build`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId }),
        signal,
      },
    ).then(readJson<BuildSubmissionDto>).then((dto) => jobRecords([dto.job])[0]),
    buildProject: (requestId, signal) => fetch(
      `${baseUrl}/build`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          mode: 'default',
          create_report: true,
          create_bundle: false,
        }),
        signal,
      },
    ).then(readJson<BuildSubmissionDto>).then((dto) => jobRecords([dto.job])[0]),
    clearPreview: (signal) => fetch(`${applicationUrl}/api/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clear_preview: true }),
      signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(await response.text())
    }),
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
    getLatestMeasurementSnapshot: async (threadId, partUuid, signal) => {
      const response = await fetch(
        `${applicationUrl}/api/measurements/threads/${encodeURIComponent(threadId)}/parts/${encodeURIComponent(partUuid)}/latest`,
        { signal, cache: 'no-store' },
      )
      if (response.status === 204) return null
      return measurementSnapshot(await readJson<MeasurementSnapshotDto>(response))
    },
    saveMeasurementSnapshot: (input, signal) => fetch(
      `${applicationUrl}/api/measurements/threads/${encodeURIComponent(input.threadId)}/parts/${encodeURIComponent(input.partUuid)}/snapshots`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(saveMeasurementBody(input)),
        signal,
      },
    ).then(async (response) => {
      if (!response.ok) throw new Error(await response.text())
    }),
  }
}

export function configuredWorkbenchClient(): WorkbenchClient {
  return window.__FLOW_CAD_WORKBENCH_CLIENT__ ?? createHttpWorkbenchClient()
}

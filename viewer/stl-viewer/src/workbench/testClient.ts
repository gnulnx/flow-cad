import type {
  DefaultThread,
  ChatProviderStatus,
  ChatTurnEvent,
  ExactFeatureLookup,
  ExactFeatureSubmission,
  InventorySnapshot,
  ProjectSummary,
  SavedMeasurementSnapshot,
  SaveMeasurementSnapshotInput,
  SendTurnInput,
  ThreadMessage,
  WorkbenchClient,
  WorkbenchJob,
} from './contracts'

export interface TestClientOverrides {
  project?: ProjectSummary | Promise<ProjectSummary>
  inventory?: InventorySnapshot | Promise<InventorySnapshot>
  jobs?: WorkbenchJob[] | Promise<WorkbenchJob[]>
  defaultThread?: DefaultThread | Promise<DefaultThread>
  sendTurn?: (input: SendTurnInput) => Promise<ThreadMessage>
  chatProvider?: ChatProviderStatus | Promise<ChatProviderStatus>
  streamTurn?: (threadId: string, turnId: string, afterSequence: number, onEvent: (event: ChatTurnEvent) => void) => Promise<void>
  exactFeatures?: ExactFeatureLookup | Promise<ExactFeatureLookup>
  queueExactFeatures?: (partUuid: string, artifactRevision: string, requestId: string) => Promise<ExactFeatureSubmission>
  latestMeasurementSnapshot?: SavedMeasurementSnapshot | null | Promise<SavedMeasurementSnapshot | null>
  saveMeasurementSnapshot?: (input: SaveMeasurementSnapshotInput) => Promise<void>
  buildPart?: (partIdentity: string, requestId: string) => Promise<WorkbenchJob>
  buildProject?: (requestId: string) => Promise<WorkbenchJob>
  clearPreview?: () => Promise<void>
}

const project: ProjectSummary = {
  projectId: 'fixture-project',
  projectName: 'Fixture Project',
  revision: 7,
  activeAssemblyId: 'active',
  gitCommit: 'abcdef1',
  gitDirty: false,
  chatAvailable: true,
}

const thread: DefaultThread = {
  thread: { id: 'default', title: 'Design review', status: 'ready' },
  messages: [],
}

export function createTestWorkbenchClient(overrides: TestClientOverrides = {}): WorkbenchClient {
  return {
    getProject: async () => overrides.project ?? project,
    getInventory: async () => overrides.inventory ?? { revision: 7, activeAssemblyId: 'active', parts: [] },
    getJobs: async () => overrides.jobs ?? [],
    getDefaultThread: async () => overrides.defaultThread ?? thread,
    getChatProvider: async () => overrides.chatProvider ?? { provider: 'test-provider', available: true, status: 'ready' },
    sendTurn: async (input) => overrides.sendTurn?.(input) ?? {
      id: `${input.requestId}-assistant`,
      role: 'assistant',
      content: 'Request accepted.',
      state: 'complete',
    },
    streamTurn: async (threadId, turnId, afterSequence, onEvent) => overrides.streamTurn?.(threadId, turnId, afterSequence, onEvent),
    buildPart: async (partIdentity, requestId) => overrides.buildPart?.(partIdentity, requestId) ?? {
      id: requestId,
      label: `Build ${partIdentity}`,
      state: 'queued',
      phase: 'queued',
      progress: 0,
      cancellable: true,
      elapsedMs: 0,
      lastUpdate: new Date(0).toISOString(),
    },
    buildProject: async (requestId) => overrides.buildProject?.(requestId) ?? {
      id: requestId,
      label: 'Build robot',
      state: 'queued',
      phase: 'queued',
      progress: 0,
      cancellable: true,
      elapsedMs: 0,
      lastUpdate: new Date(0).toISOString(),
    },
    clearPreview: async () => overrides.clearPreview?.(),
    cancelTurn: async () => undefined,
    cancelJob: async () => undefined,
    getExactFeatures: async () => overrides.exactFeatures ?? {
      status: 'job_required',
      partUuid: 'unavailable',
      artifactRevision: 'unavailable',
      geometryAuthority: 'step_kernel',
      quality: 'exact',
    },
    queueExactFeatures: async (partUuid, artifactRevision, requestId) => overrides.queueExactFeatures?.(partUuid, artifactRevision, requestId) ?? {
      status: 'queued',
      partUuid,
      artifactRevision,
      jobId: requestId,
      resultUrl: '',
    },
    getLatestMeasurementSnapshot: async () => overrides.latestMeasurementSnapshot ?? null,
    saveMeasurementSnapshot: async (input) => overrides.saveMeasurementSnapshot?.(input),
  }
}

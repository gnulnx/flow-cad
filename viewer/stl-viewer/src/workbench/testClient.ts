import type {
  DefaultThread,
  InventorySnapshot,
  ProjectSummary,
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
    getInventory: async () => overrides.inventory ?? { revision: 7, parts: [] },
    getJobs: async () => overrides.jobs ?? [],
    getDefaultThread: async () => overrides.defaultThread ?? thread,
    sendTurn: async (input) => overrides.sendTurn?.(input) ?? {
      id: `${input.requestId}-assistant`,
      role: 'assistant',
      content: 'Request accepted.',
      state: 'complete',
    },
    cancelTurn: async () => undefined,
    cancelJob: async () => undefined,
  }
}

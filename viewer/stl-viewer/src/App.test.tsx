import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BufferGeometry, Float32BufferAttribute } from 'three'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { renderVisualEvidenceCapture } from './visualEvidenceRender'

const viewerRenderProps = vi.hoisted(() => [] as Array<{ clearMeasurementsRequest: number; models: Array<Record<string, unknown>> }>)
const visualEvidenceRenderCalls = vi.hoisted(() => [] as Array<{
  models: Array<Record<string, unknown>>
  view: string
  width?: number
  height?: number
}>)

vi.mock('./components/Viewer', () => ({
  default: (props: { clearMeasurementsRequest: number; models: Array<Record<string, unknown>> }) => {
    viewerRenderProps.push(props)
    return <div data-testid="viewer">viewer</div>
  },
}))

vi.mock('./visualEvidenceRender', () => ({
  renderVisualEvidenceCapture: vi.fn(async (options: { models: Array<Record<string, unknown>>; view: string }) => {
    visualEvidenceRenderCalls.push(options)
    return {
      dataUrl: 'data:image/png;base64,T0ZGU0NSRUV4=',
      width: 960,
      height: 720,
      camera: {
        view: options.view,
        position: [1, 2, 3],
        target: [0, 0, 0],
        up: [0, 0, 1],
      },
      viewport: {
        width: 960,
        height: 720,
        render_context: 'offscreen-browser',
      },
    }
  }),
}))

const STEP_CAPABILITIES = {
  display_mesh: true,
  mesh_metrics: true,
  exact_topology: true,
  exact_snap: true,
  exact_measurement: true,
  approximate_measurement: false,
  exact_editing: false,
  mesh_only: false,
}

const MESH_ONLY_CAPABILITIES = {
  display_mesh: true,
  mesh_metrics: true,
  exact_topology: false,
  exact_snap: false,
  exact_measurement: false,
  approximate_measurement: true,
  exact_editing: false,
  mesh_only: true,
}

vi.mock('three/examples/jsm/loaders/STLLoader.js', () => ({
  STLLoader: class {
    parse() {
      const geometry = new BufferGeometry()
      geometry.setAttribute('position', new Float32BufferAttribute([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0,
      ], 3))
      return geometry
    }
  },
}))

const partsPayload = {
  revision: 0,
  active_version: 'b3_v2',
  active_assembly_id: 'b3_v2_wheel_box',
  versions: ['b3_v2'],
  parts: [
    {
      id: 'wheel_box_test_body',
      module_id: 'wheel_box',
      version: 'b3_v2',
      family: 'wheel_box',
      assembly_ids: ['b3_v2_wheel_box'],
      compatible_versions: [],
      filename: 'b3_wheel_box_test_body.step',
      role: 'printable',
      material: 'PETG',
      mass_kg: null,
      center_of_mass_mm: null,
      inertia_kg_m2: null,
      mass_source: 'unset',
      metadata_status: 'todo',
      metadata_notes: '',
      is_printable: true,
      artifact_format: 'step',
      artifact_path: 'b3/exports/step/b3_v2/wheel_box/b3_wheel_box_test_body.step',
      direct_stl_path: null,
      source_kind: 'flow_python',
      geometry_authority: 'step_kernel',
      quality_label: 'exact',
      capabilities: STEP_CAPABILITIES,
      warnings: [],
      model_url: '/api/parts/wheel_box_test_body/model',
      source_url: '/api/parts/wheel_box_test_body/source',
      snap_features_url: '/api/parts/wheel_box_test_body/snap-features',
      occurrences: [
        {
          name: 'wheel_box_test_body',
          location: [0, 0, 0],
          rotation: [0, 0, 0],
        },
      ],
      in_assembly: true,
      default_visible: true,
    },
  ],
}

const previewContextPayload = {
  component_id: 'wheel_box_test_body',
  module_id: 'wheel_box',
  family: 'wheel_box',
  version: 'b3_v2',
  role: 'printable',
  material: 'PETG',
  artifact_format: 'step',
  artifact_path: 'b3/exports/step/wheel_box/b3_wheel_box_test_body.step',
  source_context_available: true,
  source_url: '/api/parts/wheel_box_test_body/source',
  occurrences: [
    {
      name: 'wheel_box_test_body',
      location: [0, 0, 0],
      rotation: [0, 0, 0],
    },
  ],
  geometry_authority: 'step_kernel',
  quality_label: 'exact',
  capabilities: STEP_CAPABILITIES,
  warnings: [],
  source_measurements: {
    length_mm: 120,
    width_mm: 80,
    height_mm: 40,
    authority: 'step_kernel',
    source: 'part',
  },
  active_assembly_id: 'b3_v2_wheel_box',
  project_frame: {
    units: 'mm',
    origin_mm: [0, 0, 0],
    axes: {
      x_positive: 'right',
      y_positive: 'front',
      z_positive: 'top',
    },
  },
  local_frame: {
    units: 'mm',
    origin_mm: [0, 0, 0],
    rotation_deg: [0, 0, 0],
    axes: {
      x_positive: 'part-local +X',
      y_positive: 'part-local +Y',
      z_positive: 'part-local +Z',
    },
  },
  mating_contracts: {
    available: true,
    relative_path: 'docs/PART_INTERFACES.md',
    summary: 'Project mating-interface contracts live in the project part-interfaces document.',
  },
}

const draftPreviewPayload = {
  transaction_token: 'draft-preview-1',
  part_id: 'wheel_box_test_body',
  model_url: '/api/parts/wheel_box_test_body/preview-model.stl',
  display_stl_path: '/tmp/preview.stl',
  source_step_path: '/tmp/preview.step',
  geometry_authority: 'mesh',
  quality_label: 'approximate',
  facts: ['Preview generated for test'],
  warnings: ['Preview uses approximated geometry'],
  dimensions: {
    length_mm: 120,
    width_mm: 80,
    height_mm: 50,
    authority: 'mesh',
    source: 'preview',
  },
}

const proposalPayload = {
  command: 'Make this a 120 x 45 x 3 mm panel, add two M4 clearance holes 12 mm from the front edge, and put five louvers on the outside face.',
  ok: true,
  part_id: 'wheel_box_test_body',
  operations: [
    {
      name: 'create_box',
      parameters: {
        length: 120,
        width: 45,
        height: 3,
      },
    },
    {
      name: 'add_hole',
      parameters: {
        face: 'top',
        x: 50,
        y: 12,
        diameter: 4,
        through: true,
      },
    },
    {
      name: 'add_hole',
      parameters: {
        face: 'top',
        x: 70,
        y: 12,
        diameter: 4,
        through: true,
      },
    },
    {
      name: 'add_louver_pattern',
      parameters: {
        face: 'top',
        count: 5,
        pitch: 12,
        x: 60,
        y: 22.5,
        width: 10,
        height: 3,
        angle: 0,
      },
    },
  ],
  warnings: ['Outside face is ambiguous without context.'],
  assumptions: ['Assuming outside = top.'],
  errors: [],
}

const draftAcceptPayload = {
  transaction_token: 'draft-preview-1',
  source_patch_path: '/tmp/draft/source.patch',
  generated_source_path: '/tmp/draft/generated.py',
  validator_stub_path: '/tmp/draft/validator.py',
  acceptance_manifest_path: '/tmp/draft/acceptance.json',
  source_loop_commands: ['flow validate run panel-basic --draft-transaction draft-preview-1'],
  source_patch_preview: 'diff --git a/flow/parts/wheel_box_test_body.py b/flow/parts/wheel_box_test_body.py',
  command_source: 'CLI-driven preview transaction',
}

const sourcePayload = {
  component_id: 'wheel_box_test_body',
  symbol: 'make_wheel_box_test_body',
  file_path: '/repo/src/flow_cad/parts/wheel_box/prototype.py',
  relative_file_path: 'src/flow_cad/parts/wheel_box/prototype.py',
  start_line: 1,
  end_line: 5,
  highlight_start_line: 2,
  highlight_end_line: 3,
  language: 'python',
  content: [
    'from flow_cad.params import ChassisParams',
    'def make_wheel_box_test_body(params: ChassisParams):',
    '    return 42',
    '',
    'def make_wheel_box_test_top_lid(params: ChassisParams):',
  ].join('\n'),
  excerpt: '',
}

let partsRevision = 0
let healthRevision = 0
let activeParts = partsPayload.parts
let designThreads: MockDesignThread[] = []
let snapshotCounter = 0
let attachmentCounter = 0
let snapFeaturesPayload = {
  component_id: 'wheel_box_test_body',
  artifact_path: 'b3/exports/step/wheel_box/b3_wheel_box_test_body.step',
  source_format: 'step',
  features: [
    {
      id: 'line_edge:0:0.5000_0.0000_0.0000',
      kind: 'line_edge',
      label: 'Line Edge',
      point: [0.5, 0, 0],
      start: [0, 0, 0],
      end: [1, 0, 0],
      source: 'step_topology',
      quality: 'exact',
      quality_label: 'Exact',
    },
  ],
  warnings: [],
}

interface MockDesignThreadMessage {
  message_id: string
  thread_id: string
  created_at: string
  type: string
  role: string
  content: unknown
  attachments: string[]
  metadata: Record<string, unknown>
}

interface MockDesignThread {
  schema_version: number
  thread_id: string
  title: string
  status: string
  archived: boolean
  created_at: string
  updated_at: string
  messages: MockDesignThreadMessage[]
  context_snapshots: Record<string, unknown>[]
  visual_evidence?: MockVisualEvidencePayload[]
  visual_evidence_count?: number
  visual_evidence_requests?: MockVisualEvidenceRequestPayload[]
  visual_evidence_request_count?: number
  worker_jobs?: Array<Record<string, unknown>>
  worker_job_count?: number
}

interface MockAttachmentPayload {
  attachment_id: string
  kind: 'viewport_screenshot'
  content_type: 'image/png'
  selected_part_ids: string[]
  visible_part_ids: string[]
  annotations: Array<Record<string, unknown>>
  created_at: string
  metadata_path: string
  path: string
  filename: string
}

interface MockVisualEvidencePayload {
  artifact_id: string
  source: string
  view: string
  content_type: string
  path: string
  image_url: string
  image_endpoint?: string
  width: number | null
  height: number | null
  selected_ids: string[]
  visible_ids: string[]
  part_ids: string[]
  purpose: string
  created_at: string
  metadata?: Record<string, unknown>
}

interface MockVisualEvidenceRequestPayload {
  request_id: string
  thread_id: string
  status: string
  source: string
  view: string
  width?: number | null
  height?: number | null
  selected_ids: string[]
  visible_ids: string[]
  part_ids: string[]
  purpose: string | null
  created_at: string
  updated_at: string
  artifact_id: string | null
  error: string | null
  metadata?: Record<string, unknown>
}

function viewportCaptureDataUrl() {
  return 'data:image/png;base64,VGhpcyBpcyBhIHRlc3QgZGF0YSB1cmw='
}

function jsonResponse(payload: unknown) {
  return Promise.resolve(new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }))
}

function mockViewportCanvas({ dataUrl }: { dataUrl: string }) {
  const originalQuerySelector = document.querySelector.bind(document)
  const spy = vi.spyOn(document, 'querySelector')
  spy.mockImplementation((selector: string) => {
    if (selector === '.workspace-canvas canvas') {
      return {
        width: 640,
        height: 480,
        clientWidth: 640,
        clientHeight: 480,
        toDataURL: () => dataUrl,
      } as unknown as HTMLCanvasElement
    }
    return originalQuerySelector(selector)
  })
  return () => spy.mockRestore()
}

function mockMissingViewportCanvas() {
  const originalQuerySelector = document.querySelector.bind(document)
  const spy = vi.spyOn(document, 'querySelector')
  spy.mockImplementation((selector: string) => {
    if (selector === '.workspace-canvas canvas') {
      return null
    }
    return originalQuerySelector(selector)
  })
  return () => spy.mockRestore()
}

function mockArrayBufferResponse() {
  return Promise.resolve(new Response(new ArrayBuffer(8), { status: 200 }))
}

function streamResponse(chunks: string[]) {
  const encoder = new TextEncoder()
  let offset = 0
  return Promise.resolve(new Response(new ReadableStream({
    start(controller) {
      const emit = async () => {
        while (offset < chunks.length) {
          const nextChunk = chunks[offset]
          offset += 1
          await new Promise<void>((resolve) => {
            setTimeout(() => resolve(), 25)
          })
          controller.enqueue(encoder.encode(nextChunk))
        }
        controller.close()
      }

      void emit()
    },
  })))
}

function jsonBody(init: RequestInit) {
  if (typeof init.body !== 'string') return {}
  return JSON.parse(init.body) as Record<string, unknown>
}

function threadSummary(thread: MockDesignThread) {
  return {
    thread_id: thread.thread_id,
    title: thread.title,
    status: thread.status,
    archived: thread.archived,
    created_at: thread.created_at,
    updated_at: thread.updated_at,
    message_count: thread.messages.length,
  }
}

function commandTextarea() {
  return screen.getByLabelText('Command', { selector: 'textarea' }) as HTMLTextAreaElement
}

async function openAdvancedTools(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByText(/^Advanced$/))
}

async function openThreadDrawer(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Threads' }))
}

async function openEditMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Edit' }))
}

async function openAnnotateMode(user: ReturnType<typeof userEvent.setup>) {
  await openEditMenu(user)
  await user.click(screen.getByRole('menuitem', { name: 'Annotate' }))
}

function findFetchCall(suffix: string) {
  const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls as Array<[RequestInfo | URL, RequestInit]>
  return calls.find(([url]) => String(url).endsWith(suffix))
}

function requireDesignThread(title: string) {
  const thread = designThreads.find((candidate) => candidate.title === title)
  if (!thread) {
    throw new Error(`Missing mock design thread: ${title}`)
  }
  return thread
}

describe('App source loading', () => {
  beforeEach(() => {
    viewerRenderProps.length = 0
    visualEvidenceRenderCalls.length = 0
    partsRevision = 0
    healthRevision = 0
    activeParts = partsPayload.parts
    designThreads = []
    snapshotCounter = 0
    attachmentCounter = 0
    snapFeaturesPayload = {
      ...snapFeaturesPayload,
      features: [...snapFeaturesPayload.features],
      warnings: [],
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = input.toString()
      const method = init.method ?? 'GET'
      if (url.endsWith('/api/reload') && method === 'POST') {
        partsRevision += 1
        healthRevision = partsRevision
        return jsonResponse({ ok: true, revision: partsRevision })
      }
      if (url.endsWith('/api/parts')) return jsonResponse({ ...partsPayload, revision: partsRevision, parts: activeParts })
      if (url.endsWith('/api/design-threads')) {
        if (method === 'POST') {
          const body = jsonBody(init)
          const now = '2026-06-09T12:00:00Z'
          const thread: MockDesignThread = {
            schema_version: 1,
            thread_id: `thread-${designThreads.length + 1}`,
            title: String(body.title || `Thread ${designThreads.length + 1}`),
            status: 'active',
            archived: false,
            created_at: now,
            updated_at: now,
            messages: [],
            context_snapshots: [],
            visual_evidence: [],
            visual_evidence_count: 0,
            visual_evidence_requests: [],
            visual_evidence_request_count: 0,
            worker_jobs: [],
            worker_job_count: 0,
          }
          designThreads.push(thread)
          return jsonResponse(thread)
        }
        return jsonResponse({
          schema_version: 1,
          count: designThreads.length,
          threads: designThreads.map(threadSummary),
        })
      }
      const designThreadMatch = url.match(/\/api\/design-threads\/([^/]+)(?:\/(.*))?$/)
      if (designThreadMatch) {
        const threadId = designThreadMatch[1]
        const route = designThreadMatch[2] ?? ''
        const thread = designThreads.find((candidate) => candidate.thread_id === threadId)
        if (!thread) return Promise.resolve(new Response('not found', { status: 404 }))
        if (route === 'attachments/viewport-screenshot' && method === 'POST') {
          const body = jsonBody(init)
          attachmentCounter += 1
          const attachmentId = `att-${String(attachmentCounter).padStart(2, '0')}`
          const attachment: MockAttachmentPayload = {
            attachment_id: attachmentId,
            kind: 'viewport_screenshot',
            content_type: 'image/png',
            selected_part_ids: body.selected_part_ids as string[] ?? [],
            visible_part_ids: body.visible_part_ids as string[] ?? [],
            annotations: Array.isArray(body.annotations) ? body.annotations as Array<Record<string, unknown>> : [],
            created_at: '2026-06-09T12:00:30Z',
            path: `attachments/${attachmentId}.png`,
            filename: `${attachmentId}.png`,
            metadata_path: `attachments/${attachmentId}.json`,
          }

          thread.context_snapshots.push({
            schema_version: 1,
            thread_id: thread.thread_id,
            snapshot_id: `snap-att-${attachmentCounter}`,
            selected_part_ids: attachment.selected_part_ids,
            visible_part_ids: attachment.visible_part_ids,
            viewer_state: {
              viewport_screenshot: {
                kind: 'viewport_screenshot',
                attachment_id: attachment.attachment_id,
              },
              annotations: attachment.annotations,
            },
          })

          return jsonResponse(attachment)
        }
        if (route === 'visual-evidence-requests' && method === 'POST') {
          const body = jsonBody(init)
          const requestId = String(body.request_id || `ver-${(thread.visual_evidence_requests?.length ?? 0) + 1}`)
          const request: MockVisualEvidenceRequestPayload = {
            request_id: requestId,
            thread_id: threadId,
            status: 'pending',
            source: String(body.source ?? 'agent'),
            view: String(body.view ?? 'iso'),
            width: typeof body.width === 'number' ? body.width : null,
            height: typeof body.height === 'number' ? body.height : null,
            selected_ids: Array.isArray(body.selected_ids) ? body.selected_ids : [],
            visible_ids: Array.isArray(body.visible_ids) ? body.visible_ids : [],
            part_ids: Array.isArray(body.part_ids) ? body.part_ids : [],
            purpose: typeof body.purpose === 'string' ? body.purpose : null,
            created_at: '2026-06-09T12:00:35Z',
            updated_at: '2026-06-09T12:00:35Z',
            artifact_id: null,
            error: null,
            metadata: typeof body.metadata === 'object' && body.metadata !== null
              ? body.metadata as Record<string, unknown>
              : undefined,
          }
          thread.visual_evidence_requests = thread.visual_evidence_requests ?? []
          thread.visual_evidence_requests.push(request)
          thread.visual_evidence_request_count = thread.visual_evidence_requests.length
          return jsonResponse(request)
        }
        const visualEvidenceRequestMatch = route.match(/^visual-evidence-requests\/([^/]+)\/(complete|fail)$/)
        if (visualEvidenceRequestMatch && method === 'POST') {
          const requestId = visualEvidenceRequestMatch[1]
          const action = visualEvidenceRequestMatch[2]
          const request = thread.visual_evidence_requests?.find((candidate) => candidate.request_id === requestId)
          if (!request) return Promise.resolve(new Response('not found', { status: 404 }))
          const body = jsonBody(init)
          if (action === 'fail') {
            request.status = 'failed'
            request.error = String(body.error ?? 'failed')
            request.updated_at = '2026-06-09T12:00:55Z'
            return jsonResponse({ ok: true, request })
          }

          attachmentCounter += 1
          const artifactId = `ve-${String(attachmentCounter).padStart(2, '0')}`
          const evidence: MockVisualEvidencePayload = {
            artifact_id: artifactId,
            source: String(body.source ?? request.source),
            view: String(body.view ?? request.view),
            content_type: 'image/png',
            path: `visual-evidence/${artifactId}.png`,
            image_url: `/api/design-threads/${threadId}/visual-evidence/${artifactId}/image`,
            width: typeof body.width === 'number' ? body.width : null,
            height: typeof body.height === 'number' ? body.height : null,
            selected_ids: Array.isArray(body.selected_ids) ? body.selected_ids : request.selected_ids,
            visible_ids: Array.isArray(body.visible_ids) ? body.visible_ids : request.visible_ids,
            part_ids: Array.isArray(body.part_ids) ? body.part_ids : request.part_ids,
            purpose: typeof body.purpose === 'string' ? body.purpose : request.purpose ?? 'agent-request',
            created_at: '2026-06-09T12:00:50Z',
            metadata: typeof body.metadata === 'object' && body.metadata !== null
              ? body.metadata as Record<string, unknown>
              : undefined,
          }
          thread.visual_evidence = thread.visual_evidence ?? []
          thread.visual_evidence.push(evidence)
          thread.visual_evidence_count = thread.visual_evidence.length
          request.status = 'fulfilled'
          request.artifact_id = artifactId
          request.updated_at = '2026-06-09T12:00:50Z'
          return jsonResponse({ ok: true, request, visual_evidence: evidence })
        }
        if (route === 'visual-evidence-requests' && method === 'GET') {
          return jsonResponse({
            ok: true,
            thread_id: threadId,
            count: thread.visual_evidence_requests?.length ?? 0,
            visual_evidence_requests: thread.visual_evidence_requests ?? [],
          })
        }
        if (route === 'visual-evidence' && method === 'POST') {
          const body = jsonBody(init)
          attachmentCounter += 1
          const artifactId = `ve-${String(attachmentCounter).padStart(2, '0')}`
          const evidence: MockVisualEvidencePayload = {
            artifact_id: artifactId,
            source: String(body.source ?? 'manual-agent-render'),
            view: String(body.view ?? 'iso'),
            content_type: 'image/png',
            path: `visual-evidence/${artifactId}.png`,
            image_url: `/api/design-threads/${threadId}/visual-evidence/${artifactId}/image`,
            width: typeof body.width === 'number' ? body.width : null,
            height: typeof body.height === 'number' ? body.height : null,
            selected_ids: Array.isArray(body.selected_ids) ? body.selected_ids : [],
            visible_ids: Array.isArray(body.visible_ids) ? body.visible_ids : [],
            part_ids: Array.isArray(body.part_ids) ? body.part_ids : [],
            purpose: typeof body.purpose === 'string' ? body.purpose : 'manual',
            created_at: '2026-06-09T12:00:45Z',
            metadata: typeof body.metadata === 'object' && body.metadata !== null
              ? body.metadata as Record<string, unknown>
              : undefined,
          }
          thread.visual_evidence = thread.visual_evidence ?? []
          thread.visual_evidence.push(evidence)
          thread.visual_evidence_count = thread.visual_evidence.length
          return jsonResponse(evidence)
        }
        if (route === 'worker-jobs' && method === 'POST') {
          const body = jsonBody(init)
          const context = typeof body.context_snapshot === 'object' && body.context_snapshot !== null
            ? body.context_snapshot as Record<string, unknown>
            : {}
          const viewportScreenshot =
            typeof context.viewport_screenshot === 'object' && context.viewport_screenshot !== null
              ? context.viewport_screenshot as { attachment_id?: string }
              : undefined
          const attachmentId = viewportScreenshot?.attachment_id
          snapshotCounter += 1
          const snapshot = {
            schema_version: 1,
            thread_id: thread.thread_id,
            snapshot_id: `snap-${snapshotCounter}`,
            selected_part_ids: context.selected_part_ids,
            visible_part_ids: context.visible_part_ids,
            measurements: context.measurements,
            active_assembly_id: context.active_assembly_id,
            active_project_revision: context.active_project_revision,
            viewer_state: context,
          }
          if (attachmentId) {
            snapshot.viewer_state.viewport_screenshot = {
              kind: 'viewport_screenshot',
              attachment_id: attachmentId,
            }
          }
          thread.context_snapshots.push(snapshot)
          const userMessage: MockDesignThreadMessage = {
            message_id: `msg-${thread.messages.length + 1}`,
            thread_id: thread.thread_id,
            created_at: '2026-06-09T12:01:00Z',
            type: 'user_message',
            role: 'user',
            content: String(body.message || ''),
            attachments: attachmentId ? [attachmentId] : [],
            metadata: { context_snapshot_id: snapshot.snapshot_id },
          }
          if (attachmentId) {
            userMessage.metadata.viewport_screenshot = true
          }
          thread.messages.push(userMessage)

          const jobId = `job-${(thread.worker_jobs?.length ?? 0) + 1}`
          const job: Record<string, unknown> = {
            schema_version: 1,
            job_id: jobId,
            thread_id: thread.thread_id,
            status: 'running',
            created_at: '2026-06-09T12:01:00Z',
            updated_at: '2026-06-09T12:01:00Z',
            changed_paths: [],
            diff_summary: '',
            validation_evidence: [],
            commit_ready: false,
          }
          const startMessage: MockDesignThreadMessage = {
            message_id: `msg-${thread.messages.length + 1}`,
            thread_id: thread.thread_id,
            created_at: '2026-06-09T12:01:00Z',
            type: 'status',
            role: 'assistant',
            content: {
              kind: 'worker_status',
              summary: 'Starting Codex worker in the project workspace.',
              status: 'starting',
            },
            attachments: [],
            metadata: {
              runtime: 'codex_worker',
              worker_job_id: jobId,
              worker_job_status: 'queued',
              worker_job_progress: true,
              worker_progress_kind: 'status',
            },
          }
          thread.messages.push(startMessage)
          const finalMessages: MockDesignThreadMessage[] = []
          const messageText = String(body.message || '')
          const lowerMessage = messageText.toLowerCase()
          if (lowerMessage.includes('base plate')) {
            const previewPayload = {
              ...draftPreviewPayload,
              part_id: 'base_plate',
              model_url: '/api/draft-transactions/draft-preview-1/model',
              dimensions: {
                length_mm: 100,
                width_mm: 100,
                height_mm: 10,
                authority: 'mesh',
                source: 'preview',
              },
            }
            const draftEvents: MockDesignThreadMessage[] = [
              {
                message_id: `msg-${thread.messages.length + 1}`,
                thread_id: thread.thread_id,
                created_at: '2026-06-09T12:01:01Z',
                type: 'draft_event',
                role: 'assistant',
                content: {
                  action: 'propose',
                  summary: 'Proposed 1 deterministic draft operations',
                  draft_transaction_token: previewPayload.transaction_token,
                  part_id: 'base_plate',
                },
                attachments: [],
                metadata: { runtime: 'flow_cad_deterministic_draft' },
              },
              {
                message_id: `msg-${thread.messages.length + 2}`,
                thread_id: thread.thread_id,
                created_at: '2026-06-09T12:01:02Z',
                type: 'draft_event',
                role: 'assistant',
                content: {
                  action: 'apply',
                  summary: 'Applied deterministic draft operations',
                  draft_transaction_token: previewPayload.transaction_token,
                  part_id: 'base_plate',
                },
                attachments: [],
                metadata: { runtime: 'flow_cad_deterministic_draft' },
              },
              {
                message_id: `msg-${thread.messages.length + 3}`,
                thread_id: thread.thread_id,
                created_at: '2026-06-09T12:01:03Z',
                type: 'draft_event',
                role: 'assistant',
                content: {
                  action: 'preview',
                  summary: 'Draft preview generated from chat',
                  draft_transaction_token: previewPayload.transaction_token,
                  part_id: 'base_plate',
                  preview_model: previewPayload,
                },
                attachments: [],
                metadata: { runtime: 'flow_cad_deterministic_draft' },
              },
            ]
            const assistantMessage: MockDesignThreadMessage = {
              message_id: `msg-${thread.messages.length + 4}`,
              thread_id: thread.thread_id,
              created_at: '2026-06-09T12:01:04Z',
              type: 'assistant_message',
              role: 'assistant',
              content: 'Created draft `base_plate` as 100 x 100 x 10 mm.',
              attachments: [],
              metadata: {
                runtime: 'flow_cad_deterministic_draft',
                draft_transaction_token: previewPayload.transaction_token,
              },
            }
            finalMessages.push(...draftEvents, assistantMessage)
          } else {
            if (lowerMessage.includes('source change') || lowerMessage.includes('commit')) {
              job.changed_paths = ['flow/parts/panel.py']
              job.diff_summary = 'flow/parts/panel.py | 2 +-'
              job.commit_ready = true
            }
            finalMessages.push({
              message_id: `msg-${thread.messages.length + 1}`,
              thread_id: thread.thread_id,
              created_at: '2026-06-09T12:01:02Z',
              type: 'assistant_message',
              role: 'assistant',
              content: 'Codex worker response with view context.',
              attachments: [],
              metadata: {
                runtime: 'codex_worker',
                worker_job_id: jobId,
                worker_job_status: 'succeeded',
                context_snapshot_id: snapshot.snapshot_id,
                changed_paths: job.changed_paths,
                commit_ready: job.commit_ready,
                ...(attachmentId ? { viewport_screenshot: true } : {}),
              },
            })
          }
          job.final_messages = finalMessages
          job.final_sent = false
          thread.worker_jobs = thread.worker_jobs ?? []
          thread.worker_jobs.push(job)
          thread.worker_job_count = thread.worker_jobs.length
          return jsonResponse({
            thread_id: thread.thread_id,
            job,
            messages: [userMessage, startMessage],
            context_snapshot: snapshot,
            thread,
          })
        }
        const workerStreamMatch = route.match(/^worker-jobs\/([^/]+)\/stream$/)
        if (workerStreamMatch && method === 'GET') {
          const jobId = workerStreamMatch[1]
          const job = thread.worker_jobs?.find((candidate) => candidate.job_id === jobId)
          if (!job) return Promise.resolve(new Response('not found', { status: 404 }))
          const finalMessages = Array.isArray(job.final_messages)
            ? job.final_messages as MockDesignThreadMessage[]
            : []
          if (!job.final_sent) {
            thread.messages.push(...finalMessages)
            job.final_sent = true
          }
          job.status = 'succeeded'
          job.updated_at = '2026-06-09T12:01:05Z'
          job.completed_at = '2026-06-09T12:01:05Z'
          return streamResponse([
            ...finalMessages.map((message) => `data: ${JSON.stringify({ message })}\n`),
            `data: ${JSON.stringify({ done: true, job, thread })}\n`,
            'data: [DONE]\n',
          ])
        }
        const workerCommitMatch = route.match(/^worker-jobs\/([^/]+)\/commit$/)
        if (workerCommitMatch && method === 'POST') {
          const jobId = workerCommitMatch[1]
          const job = thread.worker_jobs?.find((candidate) => candidate.job_id === jobId)
          if (!job) return Promise.resolve(new Response('not found', { status: 404 }))
          job.status = 'committed'
          job.commit_ready = false
          job.commit_hash = 'abc1234'
          job.committed_at = '2026-06-09T12:02:00Z'
          const message: MockDesignThreadMessage = {
            message_id: `msg-${thread.messages.length + 1}`,
            thread_id: thread.thread_id,
            created_at: '2026-06-09T12:02:00Z',
            type: 'status',
            role: 'system',
            content: {
              summary: `Committed Codex worker job ${jobId}`,
              commit_hash: 'abc1234',
              changed_paths: job.changed_paths,
            },
            attachments: [],
            metadata: {
              worker_job_id: jobId,
              worker_job_status: 'committed',
              commit_hash: 'abc1234',
            },
          }
          thread.messages.push(message)
          return jsonResponse({ ok: true, job, message, thread })
        }
        if (route === 'chat/stream' && method === 'POST') {
          const body = jsonBody(init)
          const messageText = String(body.message || '')
          const lowerMessageText = messageText.toLowerCase()
          if (lowerMessageText.includes('base plate') || lowerMessageText.includes('100mm wide')) {
            const context = typeof body.context_snapshot === 'object' && body.context_snapshot !== null
              ? body.context_snapshot as Record<string, unknown>
              : {}
            snapshotCounter += 1
            const snapshot = {
              schema_version: 1,
              thread_id: thread.thread_id,
              snapshot_id: `snap-${snapshotCounter}`,
              selected_part_ids: context.selected_part_ids,
              visible_part_ids: context.visible_part_ids,
              measurements: context.measurements,
              active_assembly_id: context.active_assembly_id,
              active_project_revision: context.active_project_revision,
              viewer_state: context,
            }
            thread.context_snapshots.push(snapshot)
            const userMessage: MockDesignThreadMessage = {
              message_id: `msg-${thread.messages.length + 1}`,
              thread_id: thread.thread_id,
              created_at: '2026-06-09T12:01:00Z',
              type: 'user_message',
              role: 'user',
              content: messageText,
              attachments: [],
              metadata: { context_snapshot_id: snapshot.snapshot_id },
            }
            const previewPayload = {
              ...draftPreviewPayload,
              part_id: 'base_plate',
              model_url: '/api/draft-transactions/draft-preview-1/model',
              dimensions: {
                length_mm: 100,
                width_mm: 100,
                height_mm: 10,
                authority: 'mesh',
                source: 'preview',
              },
            }
            const draftEvent: MockDesignThreadMessage = {
              message_id: `msg-${thread.messages.length + 2}`,
              thread_id: thread.thread_id,
              created_at: '2026-06-09T12:01:01Z',
              type: 'draft_event',
              role: 'assistant',
              content: {
                action: 'preview',
                summary: 'Draft preview generated from chat',
                draft_transaction_token: previewPayload.transaction_token,
                part_id: 'base_plate',
                preview_model: previewPayload,
              },
              attachments: [],
              metadata: { runtime: 'flow_cad_deterministic_draft' },
            }
            const assistantMessage: MockDesignThreadMessage = {
              message_id: `msg-${thread.messages.length + 3}`,
              thread_id: thread.thread_id,
              created_at: '2026-06-09T12:01:02Z',
              type: 'assistant_message',
              role: 'assistant',
              content: 'Created draft `base_plate` as 100 x 100 x 10 mm.',
              attachments: [],
              metadata: {
                runtime: 'flow_cad_deterministic_draft',
                status: 'draft_preview_ready',
                draft_transaction_token: previewPayload.transaction_token,
                part_id: 'base_plate',
              },
            }
            thread.messages.push(userMessage, draftEvent, assistantMessage)
            return streamResponse([
              `data: ${JSON.stringify({ message: userMessage })}\n`,
              `data: ${JSON.stringify({ message: draftEvent })}\n`,
              `data: ${JSON.stringify({ message: assistantMessage })}\n`,
              `data: ${JSON.stringify({ done: true, draft_preview_model: previewPayload, thread })}\n`,
              'data: [DONE]\n',
            ])
          }
          return Promise.resolve(new Response('Not found', { status: 404 }))
        }
        if (route === 'chat' && method === 'POST') {
          const body = jsonBody(init)
          const context = typeof body.context_snapshot === 'object' && body.context_snapshot !== null
            ? body.context_snapshot as Record<string, unknown>
            : {}
          const viewportScreenshot =
            typeof context.viewport_screenshot === 'object' && context.viewport_screenshot !== null
              ? context.viewport_screenshot as { attachment_id?: string }
              : undefined
          const attachmentId = viewportScreenshot?.attachment_id
          snapshotCounter += 1
          const snapshot = {
            schema_version: 1,
            thread_id: thread.thread_id,
            snapshot_id: `snap-${snapshotCounter}`,
            selected_part_ids: context.selected_part_ids,
            visible_part_ids: context.visible_part_ids,
            measurements: context.measurements,
            active_assembly_id: context.active_assembly_id,
            active_project_revision: context.active_project_revision,
            viewer_state: context,
          }
          if (attachmentId) {
            snapshot.viewer_state.viewport_screenshot = {
              kind: 'viewport_screenshot',
              attachment_id: attachmentId,
            }
          }
          thread.context_snapshots.push(snapshot)
          const userMessage: MockDesignThreadMessage = {
            message_id: `msg-${thread.messages.length + 1}`,
            thread_id: thread.thread_id,
            created_at: '2026-06-09T12:01:00Z',
            type: 'user_message',
            role: 'user',
            content: String(body.message || ''),
            attachments: attachmentId ? [attachmentId] : [],
            metadata: { context_snapshot_id: snapshot.snapshot_id },
          }
          if (attachmentId) {
            userMessage.metadata.viewport_screenshot = true
          }
          const assistantMessage: MockDesignThreadMessage = {
            message_id: `msg-${thread.messages.length + 2}`,
            thread_id: thread.thread_id,
            created_at: '2026-06-09T12:01:02Z',
            type: 'assistant_message',
            role: 'assistant',
            content: 'Stub assistant response with view context.',
            attachments: [],
            metadata: {
              runtime: 'flow_cad_stub',
              context_snapshot_id: snapshot.snapshot_id,
              ...(attachmentId ? { viewport_screenshot: true } : {}),
            },
          }
          thread.messages.push(userMessage, assistantMessage)
          return jsonResponse({
            thread_id: thread.thread_id,
            messages: [userMessage, assistantMessage],
            context_snapshot: snapshot,
            thread,
          })
        }
        if (route === 'draft-events' && method === 'POST') {
          const body = jsonBody(init)
          const draftEvent: MockDesignThreadMessage = {
            message_id: String(body.message_id ?? `draft-event-${thread.messages.length + 1}`),
            thread_id: thread.thread_id,
            created_at: String(body.created_at ?? '2026-06-09T12:10:00Z'),
            type: String(body.type ?? 'draft_event'),
            role: String(body.role ?? 'assistant'),
            content: body.content ?? '',
            attachments: Array.isArray((body as Record<string, unknown>).attachments)
              ? (body as { attachments?: string[] }).attachments ?? []
              : [],
            metadata: typeof body.metadata === 'object' && body.metadata !== null
              ? body.metadata as Record<string, unknown>
              : {},
          }
          thread.messages.push(draftEvent)
          return jsonResponse({
            message: draftEvent,
            thread,
          })
        }
        if (route === 'messages' && method === 'POST') {
          const body = jsonBody(init)
          const message: MockDesignThreadMessage = {
            message_id: `msg-${thread.messages.length + 1}`,
            thread_id: thread.thread_id,
            created_at: '2026-06-09T12:01:00Z',
            type: String(body.type || 'user_message'),
            role: String(body.role || 'user'),
            content: body.content ?? '',
            attachments: [],
            metadata: typeof body.metadata === 'object' && body.metadata !== null
              ? body.metadata as Record<string, unknown>
              : {},
          }
          thread.messages.push(message)
          return jsonResponse(message)
        }
        if (route === 'context-snapshots' && method === 'POST') {
          const body = jsonBody(init)
          snapshotCounter += 1
          const snapshot = {
            schema_version: 1,
            thread_id: thread.thread_id,
            snapshot_id: `snap-${snapshotCounter}`,
            selected_part_ids: body.selected_part_ids,
            visible_part_ids: body.visible_part_ids,
            measurements: body.measurements,
            active_assembly_id: body.active_assembly_id,
            active_project_revision: body.active_project_revision,
          }
          thread.context_snapshots.push(snapshot)
          return jsonResponse(snapshot)
        }
        if (method === 'PATCH') {
          const body = jsonBody(init)
          if (typeof body.title === 'string') thread.title = body.title
          if (typeof body.archived === 'boolean') thread.archived = body.archived
          return jsonResponse(thread)
        }
        return jsonResponse(thread)
      }
      if (url.endsWith('/preview-context')) {
        return jsonResponse(previewContextPayload)
      }
      if (url.endsWith('/api/preview-commands/panel')) {
        return jsonResponse(proposalPayload)
      }
      if (url.endsWith('/api/imports/model') && method === 'POST') {
        return jsonResponse({
          import_id: 'import-step-01',
          part_id: 'file:loose.step',
          name: 'loose.step',
          filename: 'loose.step',
          source_format: 'step',
          source_kind: 'step',
          geometry_authority: 'step_kernel',
          quality_label: 'exact',
          capabilities: STEP_CAPABILITIES,
          warnings: [],
          model_url: '/api/imports/import-step-01/model',
          snap_features: snapFeaturesPayload.features,
        })
      }
      if (url.endsWith('/api/draft-transactions')) {
        if ((init.method ?? 'GET') === 'DELETE') {
          return jsonResponse({})
        }
        return jsonResponse({ transaction_token: draftPreviewPayload.transaction_token })
      }
      const draftTransactionMatch = url.match(/\/api\/draft-transactions\/([^/]+)\/([^/]+)$/)
      if (draftTransactionMatch) {
        const route = draftTransactionMatch[2]
        switch (route) {
          case 'box':
          case 'holes':
          case 'louver-patterns':
          case 'thickness':
            return jsonResponse({})
          case 'preview-model':
            return jsonResponse(draftPreviewPayload)
          case 'model':
            return mockArrayBufferResponse()
          case 'accept':
            return jsonResponse(draftAcceptPayload)
          default:
            break
        }
      }
      if (url.includes('/api/draft-transactions/') && init.method === 'DELETE') {
        return jsonResponse({})
      }
      if (url.endsWith('/source')) return jsonResponse(sourcePayload)
      if (url.endsWith('/snap-features')) return jsonResponse(snapFeaturesPayload)
      if (url.endsWith('/model')) {
        return mockArrayBufferResponse()
      }
      if (url.endsWith('/preview-model.stl')) {
        return mockArrayBufferResponse()
      }
      if (url.endsWith('/api/health')) return jsonResponse({ revision: healthRevision })
      return Promise.resolve(new Response('not found', { status: 404 }))
    }))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('loads full source context for the active registry part', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await user.click(screen.getByRole('tab', { name: 'Source' }))

    await screen.findByText('src/flow_cad/parts/wheel_box/prototype.py')
    expect(document.querySelector('.source-code')?.textContent).toContain('make_wheel_box_test_body')
    expect(document.querySelector('.source-code')?.textContent).toContain('make_wheel_box_test_top_lid')
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/parts/wheel_box_test_body/source')
    await waitFor(() => expect(screen.getByText('1 selected model loaded')).toBeInTheDocument())
  })

  it('shows a mesh-only warning for client-loaded STL files', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)

    await screen.findByText('wheel_box_test_body')
    const input = container.querySelector('#file-input') as HTMLInputElement
    await user.upload(input, new File(['solid loose\nendsolid loose\n'], 'loose.stl', { type: 'model/stl' }))

    await screen.findByText(/STL-only mesh/)
  })

  it('imports local STEP files through the viewer backend with exact geometry metadata', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)

    await screen.findByText('wheel_box_test_body')
    const input = container.querySelector('#file-input') as HTMLInputElement
    await user.upload(input, new File(['ISO-10303-21;\nEND-ISO-10303-21;\n'], 'loose.step', { type: 'model/step' }))

    await waitFor(() => {
      const model = viewerRenderProps.at(-1)?.models.find((candidate) => candidate.partId === 'file:loose.step')
      expect(model).toMatchObject({
        sourceKind: 'step',
        geometryAuthority: 'step_kernel',
        qualityLabel: 'exact',
        capabilities: STEP_CAPABILITIES,
        snapFeatures: snapFeaturesPayload.features,
      })
    })
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/imports/model',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Content-Type': 'application/octet-stream',
          'X-Flow-CAD-Filename': 'loose.step',
        }),
      }),
    )
  })

  it('clears measurements when health polling observes a backend revision change', async () => {
    vi.useFakeTimers()
    render(<App />)

    await vi.waitFor(() => expect(screen.getByText('1 selected model loaded')).toBeInTheDocument())
    expect(viewerRenderProps.at(-1)?.clearMeasurementsRequest).toBe(0)

    partsRevision = 1
    healthRevision = 1
    await vi.advanceTimersByTimeAsync(2000)

    await vi.waitFor(() => {
      expect(viewerRenderProps.some((props) => props.clearMeasurementsRequest > 0)).toBe(true)
    })
  })

  it('passes exact backend snap features through to the viewer model contract', async () => {
    render(<App />)

    await vi.waitFor(() => {
      const model = viewerRenderProps.at(-1)?.models[0]
      expect(model?.snapFeatures).toEqual(snapFeaturesPayload.features)
      expect(model?.capabilities).toEqual(STEP_CAPABILITIES)
      expect(model?.geometryAuthority).toBe('step_kernel')
    })
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/parts/wheel_box_test_body/snap-features')
  })

  it('passes model color mode and part color edits through to viewer models', async () => {
    const user = userEvent.setup()
    render(<App />)

    await vi.waitFor(() => {
      expect(viewerRenderProps.at(-1)?.models[0]?.color).toBe('#8b949e')
    })

    await user.click(screen.getByRole('button', { name: 'Model' }))
    await vi.waitFor(() => {
      expect(viewerRenderProps.at(-1)?.models[0]?.color).toBe('#38bdf8')
    })

    await user.click(screen.getByRole('button', { name: 'Show details for wheel_box_test_body' }))
    await user.clear(screen.getByLabelText('wheel_box_test_body display color'))
    await user.type(screen.getByLabelText('wheel_box_test_body display color'), '#ff0000')

    await vi.waitFor(() => {
      expect(viewerRenderProps.at(-1)?.models[0]?.color).toBe('#ff0000')
    })
  })

  it('does not request exact snap features for mesh-only backend models', async () => {
    activeParts = [
      {
        ...partsPayload.parts[0],
        artifact_format: 'stl',
        artifact_path: 'b3/exports/stl/wheel_box/b3_wheel_box_test_body.stl',
        direct_stl_path: 'b3/exports/stl/wheel_box/b3_wheel_box_test_body.stl',
        source_kind: 'stl',
        geometry_authority: 'mesh',
        quality_label: 'approximate',
        capabilities: MESH_ONLY_CAPABILITIES,
        warnings: ['STL-only mesh: exact CAD editing is disabled.'],
      },
    ]

    render(<App />)

    await vi.waitFor(() => {
      const model = viewerRenderProps.at(-1)?.models[0]
      expect(model?.snapFeatures).toEqual([])
      expect(model?.capabilities).toEqual(MESH_ONLY_CAPABILITIES)
      expect(model?.warnings).toEqual(['STL-only mesh: exact CAD editing is disabled.'])
    })
    expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.some(([url]) => String(url).endsWith('/snap-features'))).toBe(false)
  })

  it('loads preview context for the active part from backend payload', async () => {
    const user = userEvent.setup()

    render(<App />)
    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await openAdvancedTools(user)

    await screen.findByText('120 × 80 × 40 mm')
    expect(await screen.findAllByText('b3_v2_wheel_box')).not.toHaveLength(0)
    await screen.findByText('docs/PART_INTERFACES.md')
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/parts/wheel_box_test_body/preview-context')
  })

  it('builds a deterministic proposal from command input', async () => {
    const user = userEvent.setup()

    render(<App />)
    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await openAdvancedTools(user)

    await user.type(commandTextarea(), proposalPayload.command)
    await user.click(screen.getByRole('button', { name: 'Propose' }))

    await screen.findByText('box: resize base panel to 120 x 45 x 3 mm')
    expect(await screen.findAllByText('holes: add 4 mm clearance hole on top')).toHaveLength(2)
    await screen.findByText('louver-patterns: add 5 louver pattern on top')
    await screen.findByText('Outside face is ambiguous without context.')
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/preview-commands/panel', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        command: proposalPayload.command,
        part_id: 'wheel_box_test_body',
      }),
    }))
    expect(screen.queryByText(/Unsupported command/)).not.toBeInTheDocument()
  })

  it('loads a preview model and forwards it to viewer as draft geometry', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await openAdvancedTools(user)
    await user.type(commandTextarea(), 'Make this a 120 x 45 x 3 mm panel')

    await user.click(screen.getByRole('button', { name: 'Propose' }))
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await user.click(screen.getByRole('button', { name: 'Preview' }))

    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      const previewModel = latestModels.find((model) => model.partId === 'draft:draft-preview-1') as { color?: string } | undefined
      expect(previewModel?.color).toBe('#f97316')
    })

    expect(screen.getByText('/api/parts/wheel_box_test_body/preview-model.stl')).toBeInTheDocument()
    expect(screen.getByText('120 × 80 × 50 mm')).toBeInTheDocument()
    expect(screen.getByText('+0 × +0 × +10 mm')).toBeInTheDocument()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/draft-transactions/draft-preview-1/preview-model', {
      method: 'POST',
    })
  })

  it('auto-creates a default design thread and enables the chat composer', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await waitFor(() => {
      expect(designThreads).toHaveLength(1)
      expect(designThreads[0].title).toMatch(/^Session /)
    })

    const threadMessage = screen.getByLabelText('Thread message composer') as HTMLTextAreaElement
    expect(threadMessage).toBeEnabled()
    await user.type(threadMessage, 'Can type immediately')
    expect(threadMessage).toHaveValue('Can type immediately')
    const advancedTools = screen.getByText(/^Advanced$/).closest('details')
    expect(advancedTools).toBeInTheDocument()
    expect(advancedTools).not.toHaveAttribute('open')

    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>
    const createCall = calls.find(([url, init]) => String(url).endsWith('/api/design-threads') && (init?.method ?? 'GET') === 'POST')
    expect(createCall).toBeDefined()
    expect(jsonBody(createCall![1] as RequestInit).title).toMatch(/^Session /)
  })

  it('loads deterministic draft previews created from chat events', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.type(
      screen.getByLabelText('Thread message composer'),
      'Please create a base plate that is 100mm x 100mm x 10mm thick',
    )
    await user.click(screen.getByRole('button', { name: 'Send' }))

    await screen.findByText('Created draft `base_plate` as 100 x 100 x 10 mm.')
    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(true)
    })
    const thread = designThreads[0]
    expect(findFetchCall(`/api/design-threads/${thread.thread_id}/chat/stream`)).toBeDefined()
    expect(findFetchCall(`/api/design-threads/${thread.thread_id}/worker-jobs`)).toBeUndefined()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/draft-transactions/draft-preview-1/model')
  })

  it('routes measured rectangle and counterbore prompts to draft chat instead of the source worker', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.type(
      screen.getByLabelText('Thread message composer'),
      'I would like a part similar to this. 100mm wide, 65mm tall and 10mm thick. holes should be M4 counter bore holes',
    )
    await user.click(screen.getByRole('button', { name: 'Send' }))

    await screen.findByText('Created draft `base_plate` as 100 x 100 x 10 mm.')
    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(true)
    })
    const thread = designThreads[0]
    expect(findFetchCall(`/api/design-threads/${thread.thread_id}/chat/stream`)).toBeDefined()
    expect(findFetchCall(`/api/design-threads/${thread.thread_id}/worker-jobs`)).toBeUndefined()
  })

  it('creates a design thread, attaches viewer context, and appends a chat message', async () => {
    const user = userEvent.setup()
    const restoreCanvas = mockViewportCanvas({ dataUrl: viewportCaptureDataUrl() })

    try {
      render(<App />)

      await screen.findByText('wheel_box_test_body')
      await user.click(screen.getByText('wheel_box_test_body'))
      await openThreadDrawer(user)
      await user.type(screen.getByLabelText('New thread title'), 'Panel review')
      await user.click(screen.getByRole('button', { name: 'Create new design thread' }))

      await screen.findByText('Panel review')
      await openAnnotateMode(user)
      const toolbar = screen.getByRole('toolbar', { name: 'Annotation toolbar' })
      const markupSurface = await screen.findByLabelText('Viewport markup surface')
      await screen.findByText('Pen')
      await screen.findByRole('button', { name: 'Pen' })
      vi.spyOn(markupSurface, 'getBoundingClientRect').mockReturnValue({
        left: 0,
        top: 0,
        right: 640,
        bottom: 480,
        width: 640,
        height: 480,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      } as DOMRect)
      expect(toolbar).toBeInTheDocument()

      fireEvent.pointerDown(markupSurface, { clientX: 64, clientY: 96, pointerId: 1 })
      fireEvent.pointerMove(markupSurface, { clientX: 128, clientY: 132, pointerId: 1 })
      fireEvent.pointerMove(markupSurface, { clientX: 220, clientY: 160, pointerId: 1 })
      fireEvent.pointerUp(markupSurface, { clientX: 220, clientY: 160, pointerId: 1 })
      await screen.findByText('1 markups')

      await user.click(screen.getByRole('button', { name: 'Text' }))
      await user.type(screen.getByLabelText('Annotation text'), 'Check this edge alignment')
      fireEvent.pointerDown(markupSurface, { clientX: 320, clientY: 240, pointerId: 2 })
      await screen.findByText('2 markups')

      await user.click(screen.getByRole('button', { name: 'Attach view' }))
      const attachmentCall = await waitFor(() => {
        const value = findFetchCall('/attachments/viewport-screenshot')
        expect(value).toBeDefined()
        return value
      })

      const attachmentBody = jsonBody(attachmentCall![1] as RequestInit)
      expect(attachmentBody).toMatchObject({
        selected_part_ids: ['wheel_box_test_body'],
        visible_part_ids: ['wheel_box_test_body'],
        backend_revision: 0,
        viewport: {
          width: 640,
          height: 480,
          client_width: 640,
          client_height: 480,
        },
        data_url: viewportCaptureDataUrl(),
        annotations: [
          {
            kind: 'freehand',
            points: [
              { x: 0.1, y: 0.2 },
              { x: 0.2, y: 0.275 },
              { x: 0.34375, y: 0.3333333333333333 },
            ],
            color: '#f97316',
            width: 0.006,
          },
          {
            kind: 'note',
            text: 'Check this edge alignment',
            x: 0.5,
            y: 0.5,
          },
        ],
      })

      await waitFor(() => expect(screen.getAllByText('att-01').length).toBeGreaterThan(0))

      const composer = screen.getByLabelText('Thread message composer')
      await user.type(composer, 'Move the holes to the front face')
      await user.click(screen.getByRole('button', { name: 'Send' }))
      expect(composer).toHaveValue('')

      await screen.findByText('Move the holes to the front face')
      await screen.findByText('Stub assistant response with view context.')
      await waitFor(() => {
        const panelThread = requireDesignThread('Panel review')
        const chatCall = findFetchCall(`/api/design-threads/${panelThread.thread_id}/chat`)
        expect(chatCall).toBeDefined()
        const chatBody = jsonBody(chatCall![1] as RequestInit)
        expect(chatBody.context_snapshot).toMatchObject({
          viewport_screenshot: {
            kind: 'viewport_screenshot',
            attachment_id: 'att-01',
          },
        })
        expect(chatBody.context_snapshot).toMatchObject({
          selected_part_ids: ['wheel_box_test_body'],
          visible_part_ids: ['wheel_box_test_body'],
        })
        expect(chatBody.attachments).toEqual(['att-01'])
        expect(chatBody.metadata).toMatchObject({
          viewer_api_base: 'http://127.0.0.1:8000',
          viewport_screenshot: {
            kind: 'viewport_screenshot',
            attachment_id: 'att-01',
          },
        })
        expect(findFetchCall(`/api/design-threads/${panelThread.thread_id}/worker-jobs`)).toBeUndefined()
      })
      const panelThread = requireDesignThread('Panel review')
      expect(panelThread.context_snapshots[0]).toMatchObject({
        selected_part_ids: ['wheel_box_test_body'],
        visible_part_ids: ['wheel_box_test_body'],
      })
      expect(panelThread.messages[0]).toMatchObject({
        type: 'user_message',
        role: 'user',
        content: 'Move the holes to the front face',
        attachments: ['att-01'],
        metadata: {
          context_snapshot_id: 'snap-1',
          viewport_screenshot: true,
        },
      })
      expect(panelThread.messages.find((message) => message.type === 'assistant_message')).toMatchObject({
        type: 'assistant_message',
        role: 'assistant',
        content: 'Stub assistant response with view context.',
        metadata: {
          runtime: 'flow_cad_stub',
          context_snapshot_id: 'snap-1',
        },
      })

      await waitFor(() => expect(screen.getAllByText('att-01').length).toBeGreaterThan(0))
    } finally {
      restoreCanvas()
    }
  })

  it('moves annotation controls out of Chat and exposes them in the dedicated toolbar', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await openThreadDrawer(user)
    await user.type(screen.getByLabelText('New thread title'), 'Annotation workspace')
    await user.click(screen.getByRole('button', { name: 'Create new design thread' }))

    const chat = await screen.findByRole('region', { name: 'Design thread dock' })
    expect(within(chat).queryByRole('button', { name: 'Pen' })).not.toBeInTheDocument()
    expect(within(chat).queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()
    expect(within(chat).queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument()

    await openAnnotateMode(user)
    expect(screen.getByRole('toolbar', { name: 'Annotation toolbar' })).toBeInTheDocument()
    expect(within(chat).queryByRole('toolbar')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Close annotation toolbar' }))
    expect(screen.queryByRole('toolbar', { name: 'Annotation toolbar' })).not.toBeInTheDocument()
  })

  it('toggles annotation mode with Ctrl+A outside text inputs', async () => {
    render(<App />)

    await screen.findByText('wheel_box_test_body')
    fireEvent.keyDown(window, { key: 'a', ctrlKey: true })
    expect(screen.getByRole('toolbar', { name: 'Annotation toolbar' })).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'a', ctrlKey: true })
    expect(screen.queryByRole('toolbar', { name: 'Annotation toolbar' })).not.toBeInTheDocument()
  })

  it('does not steal Ctrl+A from text entry fields', async () => {
    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await openAnnotateMode(user)
    const annotationInput = screen.getByLabelText('Annotation text')
    await user.click(annotationInput)

    fireEvent.keyDown(annotationInput, { key: 'a', ctrlKey: true })

    expect(screen.getByRole('toolbar', { name: 'Annotation toolbar' })).toBeInTheDocument()
  })

  it('opens the local CAD picker through File > Open', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)

    const fileInput = container.querySelector('#file-input') as HTMLInputElement
    expect(fileInput).toBeInstanceOf(HTMLInputElement)
    expect(fileInput.accept).toBe('.stl,.step,.stp')

    const clickSpy = vi.spyOn(fileInput, 'click')
    await user.click(screen.getByRole('button', { name: 'File' }))
    await user.click(screen.getByRole('menuitem', { name: 'Open' }))

    expect(clickSpy).toHaveBeenCalledTimes(1)
  })

  it('posts a manual visual evidence capture to the dedicated visual-evidence endpoint', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await openThreadDrawer(user)
    await user.type(screen.getByLabelText('New thread title'), 'Render review')
    await user.click(screen.getByRole('button', { name: 'Create new design thread' }))

    await screen.findByText('Render review')
    await openAdvancedTools(user)
    await user.selectOptions(screen.getByLabelText('Visual evidence view'), 'front')
    await user.click(screen.getByRole('button', { name: 'Capture render' }))

    const visualEvidenceCall = await waitFor(() => {
      const value = findFetchCall('/visual-evidence')
      expect(value).toBeDefined()
      return value
    })
    const visualEvidenceBody = jsonBody(visualEvidenceCall![1] as RequestInit)

    expect(visualEvidenceRenderCalls).toHaveLength(1)
    expect(visualEvidenceRenderCalls[0].view).toBe('front')
    expect(visualEvidenceRenderCalls[0].models).toHaveLength(1)
    expect(visualEvidenceBody).toMatchObject({
      source: 'manual-agent-render',
      view: 'front',
      content_type: 'image/png',
      data_url: 'data:image/png;base64,T0ZGU0NSRUV4=',
      selected_ids: ['wheel_box_test_body'],
      visible_ids: ['wheel_box_test_body'],
      part_ids: ['wheel_box_test_body'],
      purpose: 'manual',
      camera: {
        view: 'front',
        position: [1, 2, 3],
        target: [0, 0, 0],
        up: [0, 0, 1],
      },
      viewport: {
        width: 960,
        height: 720,
        render_context: 'offscreen-browser',
      },
      metadata: {
        capture_source: 'separate-render-context',
        render_context: 'offscreen-browser',
      },
    })
    expect(visualEvidenceBody.width).toBe(960)
    expect(visualEvidenceBody.height).toBe(720)

    expect(findFetchCall('/attachments/viewport-screenshot')).toBeUndefined()
    await screen.findByText('id: ve-01')
    expect(await screen.findByAltText('Visual evidence front')).toBeInTheDocument()
  })

  it('fulfills pending visual evidence requests through the offscreen render worker', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await openThreadDrawer(user)
    await user.type(screen.getByLabelText('New thread title'), 'Agent visual request')
    await user.click(screen.getByRole('button', { name: 'Create new design thread' }))
    await screen.findByText('Agent visual request')
    await openAdvancedTools(user)
    await user.click(screen.getByRole('button', { name: 'Follow mode' }))
    expect(screen.getByRole('button', { name: 'Follow mode' })).toHaveAttribute('aria-pressed', 'true')

    const agentVisualThread = requireDesignThread('Agent visual request')
    agentVisualThread.visual_evidence_requests = [
      {
        request_id: 'ver-agent',
        thread_id: agentVisualThread.thread_id,
        status: 'pending',
        source: 'agent',
        view: 'top',
        width: 1200,
        height: 800,
        selected_ids: ['wheel_box_test_body'],
        visible_ids: ['wheel_box_test_body'],
        part_ids: ['wheel_box_test_body'],
        purpose: 'agent top review',
        created_at: '2026-06-09T12:02:00Z',
        updated_at: '2026-06-09T12:02:00Z',
        artifact_id: null,
        error: null,
        metadata: { caller: 'mcp' },
      },
    ]
    agentVisualThread.visual_evidence_request_count = 1

    const completeCall = await waitFor(() => {
      const value = findFetchCall('/visual-evidence-requests/ver-agent/complete')
      expect(value).toBeDefined()
      return value
    }, { timeout: 3500 })
    const completeBody = jsonBody(completeCall![1] as RequestInit)

    expect(visualEvidenceRenderCalls).toHaveLength(1)
    expect(visualEvidenceRenderCalls[0]).toMatchObject({
      view: 'top',
      width: 1200,
      height: 800,
    })
    expect(visualEvidenceRenderCalls[0].models).toHaveLength(1)
    expect(completeBody).toMatchObject({
      source: 'agent',
      view: 'top',
      request_id: 'ver-agent',
      data_url: 'data:image/png;base64,T0ZGU0NSRUV4=',
      selected_ids: ['wheel_box_test_body'],
      visible_ids: ['wheel_box_test_body'],
      part_ids: ['wheel_box_test_body'],
      purpose: 'agent top review',
      metadata: {
        caller: 'mcp',
        capture_source: 'separate-render-context',
        fulfillment_source: 'viewer-request-worker',
        render_context: 'offscreen-browser',
        visual_evidence_request_id: 'ver-agent',
      },
    })
    expect(findFetchCall('/attachments/viewport-screenshot')).toBeUndefined()
    await screen.findByText('status: fulfilled')
    await screen.findByText('artifact: ve-01')
    await waitFor(() => expect(screen.getByLabelText('Visual evidence view')).toHaveValue('top'))
  })

  it('fulfills sketch-only visual evidence requests from the viewport canvas when no model is visible', async () => {
    const user = userEvent.setup()
    const restoreCanvas = mockViewportCanvas({ dataUrl: viewportCaptureDataUrl() })

    try {
      render(<App />)

      await screen.findByText('wheel_box_test_body')
      await openThreadDrawer(user)
      await user.type(screen.getByLabelText('New thread title'), 'Sketch evidence request')
      await user.click(screen.getByRole('button', { name: 'Create new design thread' }))
      await screen.findByText('Sketch evidence request')

      const sketchThread = requireDesignThread('Sketch evidence request')
      sketchThread.visual_evidence_requests = [
        {
          request_id: 'ver-sketch',
          thread_id: sketchThread.thread_id,
          status: 'pending',
          source: 'agent',
          view: 'top',
          selected_ids: ['example_block'],
          visible_ids: [],
          part_ids: ['example_block'],
          purpose: 'capture top-view evidence for annotated draft planning',
          created_at: '2026-06-09T12:02:00Z',
          updated_at: '2026-06-09T12:02:00Z',
          artifact_id: null,
          error: null,
          metadata: { created_by: 'design_thread_chat' },
        },
      ]
      sketchThread.visual_evidence_request_count = 1

      const completeCall = await waitFor(() => {
        const value = findFetchCall('/visual-evidence-requests/ver-sketch/complete')
        expect(value).toBeDefined()
        return value
      }, { timeout: 3500 })
      const completeBody = jsonBody(completeCall![1] as RequestInit)

      expect(visualEvidenceRenderCalls).toHaveLength(0)
      expect(completeBody).toMatchObject({
        source: 'agent',
        view: 'top',
        request_id: 'ver-sketch',
        data_url: viewportCaptureDataUrl(),
        selected_ids: ['example_block'],
        visible_ids: ['wheel_box_test_body'],
        part_ids: ['example_block'],
        purpose: 'capture top-view evidence for annotated draft planning',
        metadata: {
          created_by: 'design_thread_chat',
          capture_source: 'viewport-canvas',
          fulfillment_source: 'viewer-request-worker',
          render_context: 'viewport-canvas',
          visual_evidence_request_id: 'ver-sketch',
        },
      })
      expect(completeBody.width).toBe(640)
      expect(completeBody.height).toBe(480)
      await openAdvancedTools(user)
      await screen.findByText('status: fulfilled')
      await screen.findByText('artifact: ve-01')
    } finally {
      restoreCanvas()
    }
  })

  it('records failed visual evidence requests without using user attachments', async () => {
    const user = userEvent.setup()
    vi.mocked(renderVisualEvidenceCapture).mockRejectedValueOnce(new Error('render unavailable'))

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await openThreadDrawer(user)
    await user.type(screen.getByLabelText('New thread title'), 'Failed agent request')
    await user.click(screen.getByRole('button', { name: 'Create new design thread' }))
    await screen.findByText('Failed agent request')

    const failedRequestThread = requireDesignThread('Failed agent request')
    failedRequestThread.visual_evidence_requests = [
      {
        request_id: 'ver-fail',
        thread_id: failedRequestThread.thread_id,
        status: 'pending',
        source: 'agent',
        view: 'right',
        selected_ids: ['wheel_box_test_body'],
        visible_ids: ['wheel_box_test_body'],
        part_ids: ['wheel_box_test_body'],
        purpose: 'agent side review',
        created_at: '2026-06-09T12:02:00Z',
        updated_at: '2026-06-09T12:02:00Z',
        artifact_id: null,
        error: null,
      },
    ]
    failedRequestThread.visual_evidence_request_count = 1

    const failCall = await waitFor(() => {
      const value = findFetchCall('/visual-evidence-requests/ver-fail/fail')
      expect(value).toBeDefined()
      return value
    }, { timeout: 3500 })
    const failBody = jsonBody(failCall![1] as RequestInit)

    expect(failBody.error).toBe('render unavailable')
    expect(findFetchCall('/attachments/viewport-screenshot')).toBeUndefined()
    await openAdvancedTools(user)
    await screen.findByText('status: failed')
    await screen.findByText('render unavailable')
  })

  it('recovers persisted design thread history on browser reload', async () => {
    designThreads = [
      {
        schema_version: 1,
        thread_id: 'thread-existing',
        title: 'Recovered thread',
        status: 'active',
        archived: false,
        created_at: '2026-06-09T12:00:00Z',
        updated_at: '2026-06-09T12:02:00Z',
        messages: [
          {
            message_id: 'msg-existing',
            thread_id: 'thread-existing',
            created_at: '2026-06-09T12:02:00Z',
            type: 'user_message',
            role: 'user',
            content: 'Persisted design note',
            attachments: [],
            metadata: {},
          },
        ],
        context_snapshots: [
          {
            schema_version: 1,
            thread_id: 'thread-existing',
            snapshot_id: 'snap-recovered',
            selected_part_ids: ['wheel_box_test_body'],
            visible_part_ids: ['wheel_box_test_body'],
            viewer_state: {
              viewport_screenshot: {
                kind: 'viewport_screenshot',
                attachment_id: 'att-existing',
              },
            },
          },
        ],
        visual_evidence: [
          {
            artifact_id: 've-existing',
            source: 'agent',
            view: 'front',
            content_type: 'image/png',
            path: 'visual-evidence/ve-existing.png',
            image_url: '/api/design-threads/thread-existing/visual-evidence/ve-existing/image',
            width: 640,
            height: 480,
            selected_ids: ['wheel_box_test_body'],
            visible_ids: ['wheel_box_test_body'],
            part_ids: ['wheel_box_test_body'],
            purpose: 'review',
            created_at: '2026-06-09T12:00:45Z',
            metadata: {
              source: 'agent',
            },
          },
        ],
        visual_evidence_count: 1,
      },
    ]

    const { unmount } = render(<App />)

    await screen.findByText('Recovered thread')
    await screen.findByText('Persisted design note')
    await openAdvancedTools(userEvent.setup())
    await waitFor(() => {
      expect(screen.getByText('att-existing')).toBeInTheDocument()
      expect(screen.getByText('source: agent')).toBeInTheDocument()
      expect(screen.getByText('view: front')).toBeInTheDocument()
      expect(screen.getByText('purpose: review')).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Open image' })).toHaveAttribute(
        'href',
        'http://127.0.0.1:8000/api/design-threads/thread-existing/visual-evidence/ve-existing/image',
      )
    })

    unmount()
    render(<App />)

    await screen.findByText('Recovered thread')
    await screen.findByText('Persisted design note')
    await openAdvancedTools(userEvent.setup())
    await waitFor(() => {
      expect(screen.getByText('att-existing')).toBeInTheDocument()
      expect(screen.getByText('source: agent')).toBeInTheDocument()
      expect(screen.getByText('view: front')).toBeInTheDocument()
    })
  })

  it('does not post an attachment when screenshot capture is unavailable', async () => {
    const user = userEvent.setup()
    const restoreCanvas = mockMissingViewportCanvas()

    render(<App />)
    try {
      await screen.findByText('wheel_box_test_body')
      await user.click(screen.getByText('wheel_box_test_body'))
      await openThreadDrawer(user)
      await user.type(screen.getByLabelText('New thread title'), 'No canvas thread')
      await user.click(screen.getByRole('button', { name: 'Create new design thread' }))

      await waitFor(() => expect(screen.getByText('No canvas thread')).toBeInTheDocument())
      await openAdvancedTools(user)
      await user.click(screen.getByRole('button', { name: 'Attach view' }))

      await screen.findByText('Viewport screenshot is unavailable')
      expect(findFetchCall('/attachments/viewport-screenshot')).toBeUndefined()
    } finally {
      restoreCanvas()
    }
  })

  it('switches between threads and preserves attachment history per thread', async () => {
    designThreads = [
      {
        schema_version: 1,
        thread_id: 'thread-a',
        title: 'Alpha thread',
        status: 'active',
        archived: false,
        created_at: '2026-06-09T12:00:00Z',
        updated_at: '2026-06-09T12:02:00Z',
        messages: [],
        context_snapshots: [
          {
            schema_version: 1,
            thread_id: 'thread-a',
            snapshot_id: 'snap-a',
            selected_part_ids: ['wheel_box_test_body'],
            visible_part_ids: ['wheel_box_test_body'],
            viewer_state: {
              viewport_screenshot: {
                kind: 'viewport_screenshot',
                attachment_id: 'att-alpha',
              },
            },
          },
        ],
      },
      {
        schema_version: 1,
        thread_id: 'thread-b',
        title: 'Beta thread',
        status: 'active',
        archived: false,
        created_at: '2026-06-09T12:10:00Z',
        updated_at: '2026-06-09T12:11:00Z',
        messages: [],
        context_snapshots: [],
      },
    ]

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('Alpha thread')
    await openAdvancedTools(user)
    await waitFor(() => {
      expect(screen.getByText('att-alpha')).toBeInTheDocument()
    })

    await openThreadDrawer(user)
    await user.click(await screen.findByRole('button', { name: 'Open thread Beta thread' }))

    await screen.findByText('Beta thread')
    await waitFor(() => {
      expect(screen.queryByText('att-alpha')).not.toBeInTheDocument()
      expect(screen.getByText('No attachments yet.')).toBeInTheDocument()
    })

    await openThreadDrawer(user)
    await user.click(await screen.findByRole('button', { name: 'Open thread Alpha thread' }))

    await waitFor(() => {
      expect(screen.getByText('att-alpha')).toBeInTheDocument()
    })
  })

  it('clears draft preview state on discard and accept', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await openAdvancedTools(user)
    await user.type(commandTextarea(), 'Make this a 120 x 45 x 3 mm panel')
    await user.click(screen.getByRole('button', { name: 'Propose' }))
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await user.click(screen.getByRole('button', { name: 'Preview' }))

    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(true)
    })

    await user.click(screen.getByRole('button', { name: 'Discard' }))

    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(false)
    })

    await waitFor(() => {
      expect(screen.getByText('No preview generated yet.')).toBeInTheDocument()
    })

    await user.clear(commandTextarea())
    await user.type(commandTextarea(), 'Make this a 120 x 45 x 3 mm panel')
    await user.click(screen.getByRole('button', { name: 'Propose' }))

    // Rebuild and accept to verify accept also clears draft geometry.
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await user.click(screen.getByRole('button', { name: 'Preview' }))
    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(true)
    })

    await user.click(screen.getByRole('button', { name: 'Accept' }))
    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(false)
      expect(screen.getByText('/tmp/draft/acceptance.json')).toBeInTheDocument()
      expect(screen.getByText('flow validate run panel-basic --draft-transaction draft-preview-1')).toBeInTheDocument()
      expect(screen.getByText(/diff --git a\/flow\/parts\/wheel_box_test_body.py/)).toBeInTheDocument()
    })
  })

  it('records draft action events in thread history', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await openThreadDrawer(user)
    await user.type(screen.getByLabelText('New thread title'), 'Draft action thread')
    await user.click(screen.getByRole('button', { name: 'Create new design thread' }))

    await screen.findByText('Draft action thread')
    await openAdvancedTools(user)

    await user.type(commandTextarea(), 'Make this a 120 x 45 x 3 mm panel')
    await user.click(screen.getByRole('button', { name: 'Propose' }))
    await screen.findByText(/propose: Proposed .* operations/)

    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await screen.findByText('apply: Draft operations applied')

    await user.click(screen.getByRole('button', { name: 'Preview' }))
    await screen.findByText('preview: Draft preview generated')

    await user.click(screen.getByRole('button', { name: 'Accept' }))
    await screen.findByText('accept: Draft accepted')

    await user.click(screen.getByRole('button', { name: 'Reset' }))
    await user.clear(commandTextarea())
    await user.type(commandTextarea(), 'Make this a 120 x 45 x 3 mm panel')

    await user.click(screen.getByRole('button', { name: 'Propose' }))
    await waitFor(() => {
      expect(screen.getAllByText(/propose: Proposed .* operations/)).toHaveLength(2)
    })

    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await user.click(screen.getByRole('button', { name: 'Discard' }))
    await screen.findByText('discard: Draft discarded')
  })

  it('streams assistant and tool events into chat history', async () => {
    const baselineFetch = vi.mocked(globalThis.fetch).getMockImplementation()
    if (!baselineFetch) {
      throw new Error('fetch baseline missing')
    }

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      const streamMatch = url.match(/\/api\/design-threads\/([^/]+)\/chat\/stream$/)
      if (streamMatch && init.method === 'POST') {
        const threadId = streamMatch[1]
        const thread = designThreads.find((candidate) => candidate.thread_id === threadId)
        const toolMessage = {
          type: 'tool_call',
          role: 'assistant',
          message_id: 'stream-tool',
          thread_id: threadId,
          created_at: '2026-06-09T12:20:00Z',
          content: {
            kind: 'tool_call',
            summary: 'Prepare draft geometry',
            tool: 'draft-tool',
          },
          attachments: [],
          metadata: {},
        }
        const assistantMessage = {
          type: 'assistant_message',
          role: 'assistant',
          message_id: 'stream-assistant',
          thread_id: threadId,
          created_at: '2026-06-09T12:20:01Z',
          content: 'Draft assistant response ready.',
          attachments: [],
          metadata: {},
        }
        thread?.messages.push(toolMessage, assistantMessage)
        return streamResponse([
          `data: ${JSON.stringify({ message: toolMessage })}\n`,
          `data: ${JSON.stringify({ message: assistantMessage, thread })}\n`,
        ])
      }
      return baselineFetch(input, init)
    }))

    const user = userEvent.setup()

    try {
      render(<App />)

      await screen.findByText('wheel_box_test_body')
      await user.click(screen.getByText('wheel_box_test_body'))
      await openThreadDrawer(user)
      await user.type(screen.getByLabelText('New thread title'), 'Streaming thread')
      await user.click(screen.getByRole('button', { name: 'Create new design thread' }))

      await screen.findByText('Streaming thread')
      const threadMessage = screen.getByLabelText('Thread message composer') as HTMLTextAreaElement
      await user.type(threadMessage, 'Stream this prompt')
      await user.click(screen.getByRole('button', { name: 'Send' }))

      await screen.findByText('Prepare draft geometry')
      expect(screen.queryByText('Draft assistant response ready.')).not.toBeInTheDocument()

      await waitFor(() => {
        expect(screen.getByText('Draft assistant response ready.')).toBeInTheDocument()
      })
    } finally {
      // restored automatically by afterEach via vi.unstubAllGlobals()
    }
  })

  it('routes ordinary chat through chat stream instead of starting a source worker', async () => {
    const baselineFetch = vi.mocked(globalThis.fetch).getMockImplementation()
    if (!baselineFetch) {
      throw new Error('fetch baseline missing')
    }

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      const streamMatch = url.match(/\/api\/design-threads\/([^/]+)\/chat\/stream$/)
      if (streamMatch && init.method === 'POST') {
        const threadId = streamMatch[1]
        const thread = designThreads.find((candidate) => candidate.thread_id === threadId)
        const assistantMessage = {
          type: 'assistant_message',
          role: 'assistant',
          message_id: 'chat-stream-assistant',
          thread_id: threadId,
          created_at: '2026-06-09T12:30:01Z',
          content: 'That visible block does not match the marked sketch.',
          attachments: [],
          metadata: { runtime: 'flow_cad_stub' },
        }
        thread?.messages.push(assistantMessage)
        return streamResponse([
          `data: ${JSON.stringify({ message: assistantMessage, thread })}\n`,
          `data: ${JSON.stringify({ done: true, thread })}\n`,
          'data: [DONE]\n',
        ])
      }
      return baselineFetch(input, init)
    }))

    const user = userEvent.setup()

    try {
      render(<App />)

      await screen.findByText('wheel_box_test_body')
      await openThreadDrawer(user)
      await user.type(screen.getByLabelText('New thread title'), 'Plain chat thread')
      await user.click(screen.getByRole('button', { name: 'Create new design thread' }))

      await screen.findByText('Plain chat thread')
      await user.type(screen.getByLabelText('Thread message composer'), 'does that block look anything like what I wanted?')
      await user.click(screen.getByRole('button', { name: 'Send' }))

      await screen.findByText('That visible block does not match the marked sketch.')
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
        expect(screen.getByLabelText('Thread message composer')).toBeEnabled()
      })
      const thread = requireDesignThread('Plain chat thread')
      expect(findFetchCall(`/api/design-threads/${thread.thread_id}/chat/stream`)).toBeDefined()
      expect(findFetchCall(`/api/design-threads/${thread.thread_id}/worker-jobs`)).toBeUndefined()
    } finally {
      // restored automatically by afterEach via vi.unstubAllGlobals()
    }
  })

  it('shows a commit action for completed worker jobs and calls the commit endpoint', async () => {
    const user = userEvent.setup()

    designThreads = [
      {
        schema_version: 1,
        thread_id: 'thread-commit',
        title: 'Commit worker thread',
        status: 'active',
        archived: false,
        created_at: '2026-06-09T12:00:00Z',
        updated_at: '2026-06-09T12:02:00Z',
        messages: [
          {
            message_id: 'msg-worker-done',
            thread_id: 'thread-commit',
            created_at: '2026-06-09T12:01:00Z',
            type: 'assistant_message',
            role: 'assistant',
            content: 'Codex worker response with view context.',
            attachments: [],
            metadata: {
              runtime: 'codex_worker',
              worker_job_id: 'job-1',
              worker_job_status: 'succeeded',
            },
          },
        ],
        context_snapshots: [],
        visual_evidence: [],
        visual_evidence_count: 0,
        visual_evidence_requests: [],
        visual_evidence_request_count: 0,
        worker_jobs: [
          {
            schema_version: 1,
            job_id: 'job-1',
            thread_id: 'thread-commit',
            status: 'succeeded',
            created_at: '2026-06-09T12:00:00Z',
            updated_at: '2026-06-09T12:01:00Z',
            changed_paths: ['flow/parts/panel.py'],
            diff_summary: 'flow/parts/panel.py | 2 +-',
            validation_evidence: [],
            commit_ready: true,
          },
        ],
        worker_job_count: 1,
      },
    ]

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await screen.findByText('Commit worker thread')
    await screen.findByText('Codex worker response with view context.')
    await waitFor(() => {
      const thread = requireDesignThread('Commit worker thread')
      const button = screen.getByRole('button', { name: 'Commit worker job changes' })
      expect(button).toBeEnabled()
      fireEvent.click(button)
      expect(findFetchCall(`/api/design-threads/${thread.thread_id}/worker-jobs/job-1/commit`)).toBeDefined()
      expect(thread.worker_jobs?.[0].status).toBe('committed')
    })
    await screen.findByText('Committed Codex worker job job-1')
  })
})

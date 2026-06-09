import {
  type ChangeEvent,
  type DragEvent as ReactDragEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import Viewer from './components/Viewer'
import FileDropZone from './components/FileDropZone'
import ModelList from './components/ModelList'
import Toolbar from './components/Toolbar'
import DesignThreadDock from './components/DesignThreadDock'
import ViewportMarkupOverlay from './components/ViewportMarkupOverlay'
import { calculateMeshMetrics } from './meshMetrics'
import {
  MODEL_WIREFRAME_COLOR,
  WORKBENCH_PART_COLOR,
  WORKBENCH_WIREFRAME_COLOR,
  displayColorForPart,
  draftFromPart,
  mergePartDraft,
  type ViewerColorMode,
} from './partMetadata'
import type {
  GeometryCapabilities,
  ModelData,
  PreviewContext,
  PartMetadataDraft,
  BackendPreviewOperation,
  DraftPreviewModelPayload,
  DraftAcceptanceArtifacts,
  PreviewCommandProposal,
  ProposedPreviewOperation,
  RotationMode,
  SnapFeature,
  SnapFeaturePayload,
  SourceContext,
  ViewerOccurrence,
  ViewerPart,
  ViewerPartsPayload,
  DesignThreadSummary,
  DesignThreadRecord,
  CreateDesignThreadPayload,
  DesignThreadChatPayload,
  DesignThreadChatResponse,
  DesignThreadsPayload,
  ThreadViewportMeasurement,
  ThreadViewportAnnotation,
  ViewportMarkupTool,
  ViewportAttachmentRecord,
  ViewportScreenshotPayload,
} from './types'

const IDENTITY_OCCURRENCE: ViewerOccurrence = {
  name: 'identity',
  location: [0, 0, 0],
  rotation: [0, 0, 0],
}

const MESH_ONLY_CAPABILITIES: GeometryCapabilities = {
  display_mesh: true,
  mesh_metrics: true,
  exact_topology: false,
  exact_snap: false,
  exact_measurement: false,
  approximate_measurement: true,
  exact_editing: false,
  mesh_only: true,
}

const CLIENT_STL_WARNING = 'STL-only mesh: viewing and approximate mesh measurements are available; exact CAD editing is disabled.'
const PREVIEW_MODEL_COLOR = '#f97316'
const PREVIEW_MODEL_WIREFRAME = '#fbbf24'
const PREVIEW_MODEL_WARNINGS = ['Draft preview geometry: verify with source loop before accepting.']

function extractThreadAttachmentIds(thread: DesignThreadRecord | null) {
  if (!thread) return [] as string[]
  const ids = new Set<string>()

  for (const message of thread.messages ?? []) {
    for (const attachment of message.attachments ?? []) {
      if (typeof attachment === 'string') ids.add(attachment)
    }
  }

  for (const attachment of thread.attachments ?? []) {
    if (typeof attachment.attachment_id === 'string' && attachment.attachment_id.trim()) {
      ids.add(attachment.attachment_id.trim())
    }
  }

  for (const snapshot of thread.context_snapshots ?? []) {
    if (snapshot && typeof snapshot === 'object') {
      const viewerState = (snapshot as { viewer_state?: Record<string, unknown> }).viewer_state
      if (!viewerState || typeof viewerState !== 'object') continue
      const screenshot = viewerState.viewport_screenshot
      if (screenshot && typeof screenshot === 'object') {
        const attachmentId = (screenshot as { attachment_id?: unknown }).attachment_id
        if (typeof attachmentId === 'string' && attachmentId.trim()) ids.add(attachmentId.trim())
      }
    }
  }

  return Array.from(ids)
}

type ModelStateWriter = (updater: (previous: ModelData[]) => ModelData[]) => void

function parsePositiveFloat(value: string) {
  const numeric = Number.parseFloat(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

function fallbackParsePanelCommand(command: string): { operations: ProposedPreviewOperation[]; warnings: string[] } {
  const lower = command.toLowerCase().trim()
  if (!lower) {
    return { operations: [], warnings: ['No command entered.'] }
  }

  const warnings: string[] = []
  const operations: ProposedPreviewOperation[] = []

  const dimensionMatch = lower.match(/(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)/i)
  if (dimensionMatch) {
    const length = parsePositiveFloat(dimensionMatch[1])
    const width = parsePositiveFloat(dimensionMatch[2])
    const thickness = parsePositiveFloat(dimensionMatch[3])
    if (length && width && thickness) {
      operations.push({
        kind: 'box',
        summary: `resize base panel to ${length} x ${width} x ${thickness} mm`,
        payload: {
          length,
          width,
          height: thickness,
        },
        endpoint: 'box',
      })
    }
  }

  const holeMatch = lower.match(/(\d+)\s*holes?[^\n]*(m\d+)\s*clearance/i)
  if (holeMatch) {
    const count = parsePositiveFloat(holeMatch[1])
    const diameter = parsePositiveFloat(holeMatch[2].slice(1))
    if (count && diameter) {
      operations.push({
        kind: 'hole',
        summary: `add ${count} x m${diameter} clearance holes`,
        payload: {
          face: 'front',
          count: count,
          diameter,
          x: 0,
          y: 0,
        },
        endpoint: 'holes',
      })
    }
  }

  const louverMatch = lower.match(/(\d+)\s*louver/i)
  if (louverMatch) {
    const count = parsePositiveFloat(louverMatch[1])
    if (count) {
      operations.push({
        kind: 'louver-patterns',
        summary: `add ${count} louver pattern`,
        payload: {
          face: 'front',
          count,
          pitch: 10,
          x: 0,
          y: 0,
          width: 3,
          height: 8,
          angle: 0,
        },
        endpoint: 'louver-patterns',
      })
    }
  }

  if (!operations.length) {
    warnings.push('Unsupported command: no recognized geometry operations.')
  }

  return { operations, warnings }
}

function operationSummary(operation: BackendPreviewOperation) {
  const params = operation.parameters
  if (operation.name === 'create_box') {
    return `resize base panel to ${params.length} x ${params.width} x ${params.height} mm`
  }
  if (operation.name === 'add_hole') {
    return `add ${params.diameter} mm clearance hole on ${params.face}`
  }
  if (operation.name === 'add_louver_pattern') {
    return `add ${params.count} louver pattern on ${params.face}`
  }
  if (operation.name === 'set_panel_thickness') {
    return `set panel thickness to ${params.thickness} mm`
  }
  return operation.name
}

function proposedOperationFromBackend(operation: BackendPreviewOperation): ProposedPreviewOperation | null {
  if (operation.name === 'create_box') {
    return {
      kind: 'box',
      endpoint: 'box',
      summary: operationSummary(operation),
      payload: operation.parameters,
    }
  }
  if (operation.name === 'add_hole') {
    return {
      kind: 'hole',
      endpoint: 'holes',
      summary: operationSummary(operation),
      payload: operation.parameters,
    }
  }
  if (operation.name === 'add_louver_pattern') {
    return {
      kind: 'louver-patterns',
      endpoint: 'louver-patterns',
      summary: operationSummary(operation),
      payload: operation.parameters,
    }
  }
  if (operation.name === 'set_panel_thickness') {
    return {
      kind: 'thickness',
      endpoint: 'thickness',
      summary: operationSummary(operation),
      payload: operation.parameters,
    }
  }
  return null
}

function proposalFromBackend(payload: PreviewCommandProposal) {
  const operations = payload.operations
    .map(proposedOperationFromBackend)
    .filter((operation): operation is ProposedPreviewOperation => Boolean(operation))
  return {
    operations,
    warnings: [...payload.warnings, ...payload.assumptions, ...payload.errors],
  }
}

function buildHeaders(body: unknown) {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  } satisfies RequestInit
}

function normalizeDraftEndpoint(base: string, token: string, route: string) {
  return apiUrl(base, `/api/draft-transactions/${token}/${route}`)
}

function fallbackPreviewContext(part: ViewerPart): PreviewContext {
  return {
    component_id: part.id,
    module_id: part.module_id,
    family: part.family,
    version: part.version,
    role: part.role,
    material: part.material,
    artifact_format: part.artifact_format,
    artifact_path: part.artifact_path,
    source_context_available: Boolean(part.source_url),
    source_url: part.source_url,
    occurrences: part.occurrences,
    geometry_authority: part.geometry_authority,
    quality_label: part.quality_label,
    capabilities: part.capabilities,
    warnings: part.warnings,
    source_measurements: null,
  }
}

function backendBaseUrl() {
  const params = new URLSearchParams(window.location.search)
  return (params.get('api') ?? import.meta.env.VITE_FLOW_CAD_API ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
}

function apiUrl(baseUrl: string, path: string) {
  return new URL(path, `${baseUrl}/`).toString()
}

function _uniqueModelPartIds(partIds: string[]) {
  const result: string[] = []
  const seen = new Set<string>()
  for (const partId of partIds) {
    if (seen.has(partId)) continue
    seen.add(partId)
    result.push(partId)
  }
  return result
}

function drawMarkupOnCanvas(
  context: CanvasRenderingContext2D,
  annotations: ThreadViewportAnnotation[],
  width: number,
  height: number,
) {
  context.save()
  context.lineCap = 'round'
  context.lineJoin = 'round'
  context.font = '600 18px Inter, sans-serif'
  context.textBaseline = 'middle'

  for (const annotation of annotations) {
    if (annotation.kind === 'freehand') {
      if (annotation.points.length < 2) continue
      context.strokeStyle = annotation.color ?? '#f97316'
      context.lineWidth = Math.max(2, Math.min(12, (annotation.width ?? 0.006) * Math.max(width, height)))
      context.beginPath()
      context.moveTo(annotation.points[0].x * width, annotation.points[0].y * height)
      for (const point of annotation.points.slice(1)) {
        context.lineTo(point.x * width, point.y * height)
      }
      context.stroke()
      continue
    }

    if (annotation.kind === 'circle') {
      context.strokeStyle = '#f97316'
      context.lineWidth = 4
      context.beginPath()
      context.arc(annotation.x * width, annotation.y * height, annotation.radius * Math.max(width, height), 0, Math.PI * 2)
      context.stroke()
      continue
    }

    const x = annotation.x * width
    const y = annotation.y * height
    context.fillStyle = 'rgba(7, 10, 19, 0.82)'
    context.strokeStyle = '#f97316'
    context.lineWidth = 2
    const textWidth = Math.min(width - x - 12, Math.max(72, context.measureText(annotation.text).width + 18))
    context.fillRect(x + 12, y - 24, textWidth, 34)
    context.strokeRect(x + 12, y - 24, textWidth, 34)
    context.fillStyle = '#fff7ed'
    context.fillText(annotation.text, x + 21, y - 7, textWidth - 18)
    context.beginPath()
    context.arc(x, y, 6, 0, Math.PI * 2)
    context.fillStyle = '#f97316'
    context.fill()
  }

  context.restore()
}

function captureViewportScreenshot(annotations: ThreadViewportAnnotation[] = []) {
  const canvas = document.querySelector('.workspace-canvas canvas') as HTMLCanvasElement | null
  if (!canvas) return { viewportSize: null, screenshot: null }

  const viewportSize = {
    width: canvas.width,
    height: canvas.height,
    client_width: canvas.clientWidth,
    client_height: canvas.clientHeight,
  }

  try {
    if (annotations.length) {
      const compositeCanvas = document.createElement('canvas')
      compositeCanvas.width = canvas.width
      compositeCanvas.height = canvas.height
      const context = compositeCanvas.getContext('2d')
      if (context) {
        context.drawImage(canvas, 0, 0, canvas.width, canvas.height)
        drawMarkupOnCanvas(context, annotations, canvas.width, canvas.height)
        return {
          viewportSize,
          screenshot: {
            kind: 'viewport_screenshot',
            content_type: 'image/png',
            data_url: compositeCanvas.toDataURL('image/png'),
          },
        }
      }
    }
    return {
      viewportSize,
      screenshot: {
        kind: 'viewport_screenshot',
        content_type: 'image/png',
        data_url: canvas.toDataURL('image/png'),
      },
    }
  } catch (error) {
    console.warn('Could not capture viewport screenshot:', error)
    return { viewportSize, screenshot: null }
  }
}

async function responseDetail(response: Response) {
  try {
    const payload = await response.json()
    return payload.detail ?? `${response.status} ${response.statusText}`
  } catch {
    return `${response.status} ${response.statusText}`
  }
}

export default function App() {
  const apiBase = useMemo(() => backendBaseUrl(), [])
  const [parts, setParts] = useState<ViewerPart[]>([])
  const [models, setModels] = useState<ModelData[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [activeName, setActiveName] = useState<string | null>(null)
  const [sourceContext, setSourceContext] = useState<SourceContext | null>(null)
  const [statusMessage, setStatusMessage] = useState('Loading viewer state...')
  const backendRevisionRef = useRef<number | null>(null)
  const [sourceCollapsed, setSourceCollapsed] = useState(false)
  const [partsCollapsed, setPartsCollapsed] = useState(false)
  const [rotationMode, setRotationMode] = useState<RotationMode>('turntable')
  const [tapeMode, setTapeMode] = useState(false)
  const [clearMeasurementsRequest, setClearMeasurementsRequest] = useState(0)
  const [isDragOver, setIsDragOver] = useState(false)
  const [fitRequest, setFitRequest] = useState(0)
  const [frameSelectedRequest, setFrameSelectedRequest] = useState(0)
  const [projectName, setProjectName] = useState<string | null>(null)
  const [activeVersion, setActiveVersion] = useState<string | null>(null)
  const [activeAssemblyId, setActiveAssemblyId] = useState<string | null>(null)
  const [colorMode, setColorMode] = useState<ViewerColorMode>('workbench')
  const [leftDockTab, setLeftDockTab] = useState<'source' | 'chat'>('chat')
  const [partMetadataDrafts, setPartMetadataDrafts] = useState<Record<string, PartMetadataDraft>>({})
  const [previewContext, setPreviewContext] = useState<PreviewContext | null>(null)
  const [previewCommand, setPreviewCommand] = useState('')
  const [proposedOperations, setProposedOperations] = useState<ProposedPreviewOperation[]>([])
  const [proposalWarnings, setProposalWarnings] = useState<string[]>([])
  const [draftTransactionToken, setDraftTransactionToken] = useState<string | null>(null)
  const [previewModelPayload, setPreviewModelPayload] = useState<DraftPreviewModelPayload | null>(null)
  const [acceptanceArtifacts, setAcceptanceArtifacts] = useState<DraftAcceptanceArtifacts | null>(null)
  const [previewModels, setPreviewModels] = useState<ModelData[]>([])
  const [commandBusy, setCommandBusy] = useState({
    propose: false,
    apply: false,
    preview: false,
    accept: false,
    discard: false,
  })
  const loadingPartIdsRef = useRef<Set<string>>(new Set())
  const [threadSummaries, setThreadSummaries] = useState<DesignThreadSummary[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [activeThread, setActiveThread] = useState<DesignThreadRecord | null>(null)
  const [threadBusy, setThreadBusy] = useState(false)
  const [threadAttachmentIds, setThreadAttachmentIds] = useState<string[]>([])
  const [latestAttachmentId, setLatestAttachmentId] = useState<string | null>(null)
  const [markupActive, setMarkupActive] = useState(false)
  const [markupTool, setMarkupTool] = useState<ViewportMarkupTool>('pen')
  const [markupNoteText, setMarkupNoteText] = useState('')
  const [viewportAnnotations, setViewportAnnotations] = useState<ThreadViewportAnnotation[]>([])

  // Resizing state hooks
  const [sourceWidth, setSourceWidth] = useState(380)
  const [partsWidth, setPartsWidth] = useState(380)
  const [isResizingSource, setIsResizingSource] = useState(false)
  const [isResizingParts, setIsResizingParts] = useState(false)

  const loadStlBuffer = useCallback((
    name: string,
    partId: string,
    occurrences: ViewerOccurrence[],
    content: ArrayBuffer,
    snapFeatures: SnapFeature[] = [],
    geometryMetadata: {
      sourceKind: ModelData['sourceKind']
      geometryAuthority: ModelData['geometryAuthority']
      qualityLabel: ModelData['qualityLabel']
      capabilities: GeometryCapabilities
      warnings: string[]
    } = {
      sourceKind: 'client_stl',
      geometryAuthority: 'mesh',
      qualityLabel: 'approximate',
      capabilities: MESH_ONLY_CAPABILITIES,
      warnings: [CLIENT_STL_WARNING],
    },
    targetModelState: ModelStateWriter = setModels,
  ) => {
    const geometry = new STLLoader().parse(content)
    geometry.computeVertexNormals()
    geometry.computeBoundingBox()
    geometry.computeBoundingSphere()

    const metrics = calculateMeshMetrics(geometry)

    const model: ModelData = {
      name,
      partId,
      geometry,
      color: '#5ec4ff',
      wireframeColor: '#f4d35e',
      snapFeatures,
      ...geometryMetadata,
      occurrences,
      bounds: {
        min: metrics.bounds.min.clone(),
        max: metrics.bounds.max.clone(),
        size: metrics.bounds.size.clone(),
        center: metrics.bounds.center.clone(),
      },
      metrics,
    }

    targetModelState((prev) => {
      const remaining = prev.filter((existing) => existing.partId !== partId)
      return [...remaining, model]
    })
  }, [])

  const loadSnapFeatures = useCallback(async (part: ViewerPart) => {
    if (!part.snap_features_url) return []
    const response = await fetch(apiUrl(apiBase, part.snap_features_url))
    if (!response.ok) {
      console.warn(`${part.id}: snap features unavailable: ${await responseDetail(response)}`)
      return []
    }
    const payload = await response.json() as SnapFeaturePayload
    return payload.features
  }, [apiBase])

  const loadPartModel = useCallback(async (part: ViewerPart) => {
    if (!part.artifact_format) return null

    const response = await fetch(apiUrl(apiBase, part.model_url))
    if (!response.ok) {
      throw new Error(`${part.id}: ${await responseDetail(response)}`)
    }
    const content = await response.arrayBuffer()
    const snapFeatures = part.capabilities.exact_snap ? await loadSnapFeatures(part) : []
    loadStlBuffer(
      part.id,
      part.id,
      part.occurrences.length ? part.occurrences : [IDENTITY_OCCURRENCE],
      content,
      snapFeatures,
      {
        sourceKind: part.source_kind,
        geometryAuthority: part.geometry_authority,
        qualityLabel: part.quality_label,
        capabilities: part.capabilities,
        warnings: part.warnings,
      },
    )
    return part.id
  }, [apiBase, loadSnapFeatures, loadStlBuffer])

  const loadViewerState = useCallback(async () => {
    setStatusMessage('Loading registry parts...')
    const response = await fetch(apiUrl(apiBase, '/api/parts'))
    if (!response.ok) {
      throw new Error(await responseDetail(response))
    }
    const payload = await response.json() as ViewerPartsPayload
    if (payload.project_name) {
      setProjectName(payload.project_name)
    }
    setActiveVersion(payload.active_version ?? null)
    setActiveAssemblyId(payload.active_assembly_id ?? null)
    const previousRevision = backendRevisionRef.current
    if (previousRevision !== null && payload.revision !== previousRevision) {
      setModels((prev) => prev.filter((model) => model.partId.startsWith('file:') || model.partId.startsWith('url:')))
      setPreviewModels([])
      setPreviewModelPayload(null)
      setDraftTransactionToken(null)
      setAcceptanceArtifacts(null)
      setSourceContext(null)
      setActiveName(null)
      setClearMeasurementsRequest((value) => value + 1)
    }
    backendRevisionRef.current = payload.revision
    setParts(payload.parts)
    const availablePartIds = new Set(payload.parts.map((part) => part.id))
    setModels((prev) => prev.filter((model) => model.partId.startsWith('file:') || model.partId.startsWith('url:') || availablePartIds.has(model.partId)))
    setSelectedIds((prev) => {
      const availableIds = new Set(payload.parts.map((part) => part.id))
      const kept = prev.filter((id) => availableIds.has(id))
      if (kept.length) return kept
      const assembledIds = payload.parts.filter((part) => part.default_visible).map((part) => part.id)
      return assembledIds.length ? assembledIds : payload.parts.map((part) => part.id)
    })
    setStatusMessage(`${payload.parts.length} parts indexed`)
  }, [apiBase])

  const loadThread = useCallback(async (threadId: string) => {
    const response = await fetch(apiUrl(apiBase, `/api/design-threads/${threadId}`))
    if (!response.ok) {
      throw new Error(await responseDetail(response))
    }
    const payload = await response.json() as DesignThreadRecord
    setActiveThread(payload)
    setActiveThreadId(threadId)
    const attachmentIds = extractThreadAttachmentIds(payload)
    setThreadAttachmentIds(attachmentIds)
    setLatestAttachmentId(attachmentIds.at(-1) ?? null)
    return payload
  }, [apiBase])

  const loadThreadSummaries = useCallback(async (options: { autoSelect?: boolean } = {}) => {
    const { autoSelect = false } = options
    setThreadBusy(true)
    try {
      const response = await fetch(apiUrl(apiBase, '/api/design-threads'))
      if (!response.ok) {
        return
      }
      const payload = await response.json() as DesignThreadsPayload
      const nextThreads = payload.threads ?? []
      setThreadSummaries(nextThreads)
      if (autoSelect && !activeThreadId && nextThreads[0]) {
        await loadThread(nextThreads[0].thread_id)
      }
    } catch (error) {
      console.error('Failed to load design threads:', error)
    } finally {
      setThreadBusy(false)
    }
  }, [activeThreadId, apiBase, loadThread])

  const createThread = useCallback(async (payload: CreateDesignThreadPayload) => {
    setThreadBusy(true)
    try {
      const response = await fetch(apiUrl(apiBase, '/api/design-threads'), {
        ...buildHeaders(payload),
      })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }
      const created = await response.json() as DesignThreadRecord
      await loadThread(created.thread_id)
      await loadThreadSummaries()
    } finally {
      setThreadBusy(false)
    }
  }, [apiBase, loadThread, loadThreadSummaries])

  const patchThread = useCallback(async (threadId: string, patch: Record<string, unknown>) => {
    const response = await fetch(apiUrl(apiBase, `/api/design-threads/${threadId}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (!response.ok) {
      throw new Error(await responseDetail(response))
    }
    const payload = await response.json() as DesignThreadRecord
    if (payload.thread_id === activeThreadId) {
      setActiveThread(payload)
    }
    await loadThreadSummaries()
    return payload
  }, [apiBase, activeThreadId, loadThreadSummaries])

  const createViewportAttachment = useCallback(async (threadId: string, payload: ViewportScreenshotPayload) => {
    const response = await fetch(apiUrl(apiBase, `/api/design-threads/${threadId}/attachments/viewport-screenshot`), {
      ...buildHeaders(payload),
    })
    if (!response.ok) {
      throw new Error(await responseDetail(response))
    }
    const attachment = await response.json() as ViewportAttachmentRecord
    await loadThread(threadId)
    setLatestAttachmentId(attachment.attachment_id)
    setThreadAttachmentIds((current) =>
      current.includes(attachment.attachment_id) ? current : [...current, attachment.attachment_id],
    )
    return attachment
  }, [apiBase, loadThread])

  const sendThreadChatMessage = useCallback(async (threadId: string, payload: DesignThreadChatPayload) => {
    const contextSnapshot = payload.context_snapshot
    const normalizedContextSnapshot =
      contextSnapshot && typeof contextSnapshot === 'object' && !Array.isArray(contextSnapshot)
        ? { ...contextSnapshot }
        : {}
    if ('viewport_screenshot' in normalizedContextSnapshot) {
      delete normalizedContextSnapshot.viewport_screenshot
    }
    const payloadWithAttachment = {
      ...payload,
      ...(latestAttachmentId
        ? {
          attachments: [latestAttachmentId],
          metadata: {
            ...(payload.metadata ?? {}),
            viewport_screenshot: {
              kind: 'viewport_screenshot',
              attachment_id: latestAttachmentId,
            },
          },
        }
        : {}),
      context_snapshot: {
        ...normalizedContextSnapshot,
        ...(latestAttachmentId
          ? {
            viewport_screenshot: {
              kind: 'viewport_screenshot',
              attachment_id: latestAttachmentId,
            },
          }
          : {}),
      },
    }
    const response = await fetch(apiUrl(apiBase, `/api/design-threads/${threadId}/chat`), buildHeaders(payloadWithAttachment))
    if (!response.ok) {
      throw new Error(await responseDetail(response))
    }
    const chat = await response.json() as DesignThreadChatResponse
    setActiveThread(chat.thread)
    setActiveThreadId(threadId)
    setThreadAttachmentIds(extractThreadAttachmentIds(chat.thread))
    setLatestAttachmentId((chat.thread.context_snapshots ?? []).at(-1)?.viewer_state?.viewport_screenshot?.attachment_id ?? latestAttachmentId)
    await loadThreadSummaries()
    return chat
  }, [apiBase, loadThreadSummaries, latestAttachmentId])

  const viewerParts = useMemo(
    () => parts.map((part) => mergePartDraft(part, partMetadataDrafts[part.id])),
    [partMetadataDrafts, parts],
  )

  const clearDraftState = useCallback(() => {
    setDraftTransactionToken(null)
    setPreviewContext(null)
    setPreviewCommand('')
    setProposedOperations([])
    setProposalWarnings([])
    setPreviewModelPayload(null)
    setAcceptanceArtifacts(null)
    setPreviewModels([])
  }, [])

  const setBusy = useCallback((action: keyof typeof commandBusy, busy: boolean) => {
    setCommandBusy((current) => ({ ...current, [action]: busy }))
  }, [])

  const activePreviewPartRef = useRef<string | null>(null)

  useEffect(() => {
    if (activePreviewPartRef.current === activeName) return
    activePreviewPartRef.current = activeName
    clearDraftState()
  }, [activeName, clearDraftState])

  const handlePartMetadataChange = useCallback((partId: string, patch: Partial<PartMetadataDraft>) => {
    setPartMetadataDrafts((current) => {
      const part = parts.find((candidate) => candidate.id === partId)
      if (!part) return current
      return {
        ...current,
        [partId]: {
          ...draftFromPart(part),
          ...current[partId],
          ...patch,
        },
      }
    })
  }, [parts])

  const handlePartMetadataReset = useCallback((partId: string) => {
    setPartMetadataDrafts((current) => {
      if (!(partId in current)) return current
      const next = { ...current }
      delete next[partId]
      return next
    })
  }, [])

  useEffect(() => {
    if (!viewerParts.length || !selectedIds.length) return

    const loadedIds = new Set(models.map((model) => model.partId))
    const selectedParts = selectedIds
      .map((id) => viewerParts.find((part) => part.id === id))
      .filter((part): part is ViewerPart => Boolean(part))
    const missingParts = selectedParts.filter((part) => {
      if (!part.artifact_format) return false
      if (loadedIds.has(part.id)) return false
      return !loadingPartIdsRef.current.has(part.id)
    })
    if (!missingParts.length) return

    missingParts.forEach((part) => loadingPartIdsRef.current.add(part.id))
    setStatusMessage(`Loading ${missingParts.length} selected model${missingParts.length === 1 ? '' : 's'}...`)

    Promise.allSettled(missingParts.map((part) => loadPartModel(part)))
      .then((results) => {
        missingParts.forEach((part) => loadingPartIdsRef.current.delete(part.id))
        const failures = results.filter((result): result is PromiseRejectedResult => result.status === 'rejected')
        if (failures.length) {
          setStatusMessage(`${missingParts.length - failures.length}/${missingParts.length} selected models loaded; ${failures[0].reason}`)
        } else {
          setStatusMessage(`${selectedParts.length} selected model${selectedParts.length === 1 ? '' : 's'} loaded`)
        }
        setFitRequest((value) => value + 1)
      })
      .catch((err) => {
        missingParts.forEach((part) => loadingPartIdsRef.current.delete(part.id))
        setStatusMessage(`Model load failed: ${err.message}`)
      })
  }, [loadPartModel, models, selectedIds, viewerParts])

  const reloadViewer = useCallback(async () => {
    setStatusMessage('Reloading viewer...')
    const reloadResponse = await fetch(apiUrl(apiBase, '/api/reload'), { method: 'POST' })
    if (!reloadResponse.ok) {
      throw new Error(await responseDetail(reloadResponse))
    }
    clearDraftState()
    await loadViewerState()
  }, [apiBase, clearDraftState, loadViewerState])

  const loadStlFile = useCallback((file: File) => {
    const reader = new FileReader()

    reader.onload = (e) => {
      try {
        const content = e.target?.result
        if (!(content instanceof ArrayBuffer)) {
          throw new Error('FileReader did not return STL binary content')
        }
        const partId = `file:${file.name}`
        loadStlBuffer(file.name, partId, [IDENTITY_OCCURRENCE], content)
        setSelectedIds((prev) => [...prev.filter((id) => id !== partId), partId])
        setActiveName(partId)
        setFitRequest((value) => value + 1)
      } catch (err) {
        console.error(`Failed to parse ${file.name}:`, err)
      }
    }

    reader.onerror = () => console.error(`Failed to read ${file.name}:`, reader.error)
    reader.readAsArrayBuffer(file)
  }, [loadStlBuffer])

  useEffect(() => {
    const requestedStl = new URLSearchParams(window.location.search).get('stl')
    if (!requestedStl) return

    const loadRequestedStl = async () => {
      try {
        const response = await fetch(requestedStl)
        if (!response.ok) {
          throw new Error(`${response.status} ${response.statusText}`)
        }
        const content = await response.arrayBuffer()
        const name = requestedStl.split('/').pop() ?? requestedStl
        const partId = `url:${requestedStl}`
        loadStlBuffer(name, partId, [IDENTITY_OCCURRENCE], content)
        setSelectedIds((prev) => [...prev.filter((id) => id !== partId), partId])
        setActiveName(partId)
        setFitRequest((value) => value + 1)
      } catch (err) {
        console.error(`Failed to load ${requestedStl}:`, err)
      }
    }

    void loadRequestedStl()
  }, [loadStlBuffer])

  useEffect(() => {
    loadViewerState().catch((err) => {
      console.error('Failed to load viewer state:', err)
      setStatusMessage(`Viewer API unavailable: ${err.message}`)
    })
  }, [loadViewerState])

  useEffect(() => {
    loadThreadSummaries({ autoSelect: true }).catch((err) => {
      console.error('Failed to load design threads:', err)
    })
  }, [loadThreadSummaries])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      fetch(apiUrl(apiBase, '/api/health'))
        .then(async (response) => {
          if (!response.ok) throw new Error(await responseDetail(response))
          return response.json() as Promise<{ revision: number }>
        })
        .then((payload) => {
          const currentRevision = backendRevisionRef.current
          if (currentRevision !== null && payload.revision > currentRevision) {
            loadViewerState().catch((err) => {
              console.error('Failed to refresh viewer state:', err)
              setStatusMessage(`Refresh failed: ${err.message}`)
            })
          } else if (currentRevision === null) {
            backendRevisionRef.current = payload.revision
          }
        })
        .catch(() => {
          // The main load path already reports API availability; avoid noisy polling status churn.
        })
    }, 2000)

    return () => window.clearInterval(intervalId)
  }, [apiBase, loadViewerState])

  useEffect(() => {
    if (!activeName || activeName.startsWith('file:') || activeName.startsWith('url:')) {
      setSourceContext(null)
      return
    }

    const part = viewerParts.find((candidate) => candidate.id === activeName)
    if (!part) {
      setSourceContext(null)
      return
    }

    const loadSource = async () => {
      const response = await fetch(apiUrl(apiBase, part.source_url))
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }
      setSourceContext(await response.json() as SourceContext)
    }

    loadSource().catch((err) => {
      console.error(`Failed to load source for ${activeName}:`, err)
      setSourceContext(null)
    })
  }, [activeName, apiBase, viewerParts])

  useEffect(() => {
    if (!activeName || activeName.startsWith('file:') || activeName.startsWith('url:')) {
      setPreviewContext(null)
      return
    }

    const part = viewerParts.find((candidate) => candidate.id === activeName)
    if (!part) {
      setPreviewContext(null)
      return
    }

    const loadPreviewContext = async () => {
      const response = await fetch(apiUrl(apiBase, `/api/parts/${activeName}/preview-context`))
      if (!response.ok) {
        setPreviewContext(fallbackPreviewContext(part))
        return
      }
      setPreviewContext(await response.json() as PreviewContext)
    }

    loadPreviewContext().catch((err) => {
      console.error(`Failed to load preview context for ${activeName}:`, err)
      setPreviewContext(fallbackPreviewContext(part))
    })
  }, [activeName, apiBase, viewerParts])

  const handleFiles = useCallback((files: FileList) => {
    const stlFiles = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.stl'))
    if (stlFiles.length === 0) {
      console.log('No STL files in:', Array.from(files).map(f => f.name))
      return
    }

    setIsDragOver(false)

    stlFiles.forEach(file => {
      console.log('Loading:', file.name, 'type:', file.type, 'size:', file.size)
      loadStlFile(file)
    })
  }, [loadStlFile])

  const handleDrop = useCallback((e: ReactDragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    console.log('Drop event on FileDropZone')
    if (e.dataTransfer.files.length) {
      handleFiles(e.dataTransfer.files)
    }
    setIsDragOver(false)
  }, [handleFiles])

  const handleDragOver = useCallback((e: ReactDragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
  }, [])

  const handleDragLeave = useCallback((e: ReactDragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
  }, [])

  const handleFileSelect = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      handleFiles(e.target.files)
      e.target.value = ''
    }
  }, [handleFiles])

  const handlePreviewCommandChange = useCallback((value: string) => {
    setPreviewCommand(value)
  }, [])

  const selectedPart = activeName ? viewerParts.find((part) => part.id === activeName) ?? null : null

  const handlePropose = useCallback(async () => {
    setBusy('propose', true)
    try {
      let parsed: { operations: ProposedPreviewOperation[]; warnings: string[] }
      try {
        const response = await fetch(
          apiUrl(apiBase, '/api/preview-commands/panel'),
          buildHeaders({
            command: previewCommand,
            part_id: selectedPart?.id,
          }),
        )
        if (!response.ok) {
          throw new Error(await responseDetail(response))
        }
        parsed = proposalFromBackend(await response.json() as PreviewCommandProposal)
      } catch (err) {
        console.warn('Falling back to client-side preview command parser:', err)
        parsed = fallbackParsePanelCommand(previewCommand)
      }

      setProposedOperations(parsed.operations)
      setProposalWarnings(parsed.warnings)
      if (!parsed.operations.length) {
        setStatusMessage('No operations proposed. Update command input.')
      } else {
        setStatusMessage(`Proposed ${parsed.operations.length} operation${parsed.operations.length === 1 ? '' : 's'}.`)
      }
    } finally {
      setBusy('propose', false)
    }
  }, [apiBase, previewCommand, selectedPart])

  const applyOperations = useCallback(async (transactionToken: string) => {
    if (!selectedPart) return

    for (const operation of proposedOperations) {
      const payload = {
        part_id: selectedPart.id,
        ...operation.payload,
      }
      const response = await fetch(normalizeDraftEndpoint(apiBase, transactionToken, operation.endpoint), buildHeaders(payload))
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }
    }
  }, [apiBase, proposedOperations, selectedPart])

  const handleApply = useCallback(async () => {
    if (!activeName || !selectedPart) return
    if (!proposedOperations.length) {
      setProposalWarnings(['No proposed operations to apply.'])
      return
    }

    setBusy('apply', true)
    try {
      let transactionToken = draftTransactionToken
      if (!transactionToken) {
        const response = await fetch(
          apiUrl(apiBase, '/api/draft-transactions'),
          buildHeaders({ part_id: selectedPart.id, module_id: selectedPart.module_id }),
        )
        if (!response.ok) {
          throw new Error(await responseDetail(response))
        }
        const payload = await response.json() as { transaction_token: string }
        transactionToken = payload.transaction_token
        setDraftTransactionToken(transactionToken)
      }

      await applyOperations(transactionToken)
      setPreviewModelPayload(null)
      setPreviewModels([])
      setStatusMessage('Draft operations applied. Generate preview when ready.')
    } catch (err) {
      console.error('Failed to apply operations:', err)
      setStatusMessage(`Failed to apply draft operations: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy('apply', false)
    }
  }, [activeName, applyOperations, apiBase, draftTransactionToken, proposedOperations, selectedPart])

  const loadPreviewModel = useCallback(async (token: string) => {
    let response = await fetch(normalizeDraftEndpoint(apiBase, token, 'preview-model'), { method: 'POST' })
    if (!response.ok) {
      response = await fetch(normalizeDraftEndpoint(apiBase, token, 'preview'), { method: 'POST' })
    }
    if (!response.ok) {
      throw new Error(await responseDetail(response))
    }

    const payload = await response.json() as DraftPreviewModelPayload
    setPreviewModelPayload(payload)

    if (!selectedPart) {
      return
    }

    const modelResponse = await fetch(apiUrl(apiBase, payload.model_url))
    if (!modelResponse.ok) {
      throw new Error(await responseDetail(modelResponse))
    }
    const content = await modelResponse.arrayBuffer()
    loadStlBuffer(
      `preview:${payload.transaction_token}`,
      `draft:${payload.transaction_token}`,
      selectedPart.occurrences.length ? selectedPart.occurrences : [IDENTITY_OCCURRENCE],
      content,
      [],
      {
        sourceKind: 'client_stl',
        geometryAuthority: payload.geometry_authority,
        qualityLabel: payload.quality_label,
        capabilities: {
          ...MESH_ONLY_CAPABILITIES,
          exact_topology: payload.geometry_authority === 'step_kernel',
          exact_measurement: payload.geometry_authority === 'step_kernel',
          exact_editing: false,
        },
        warnings: Array.from(new Set([...PREVIEW_MODEL_WARNINGS, ...payload.warnings, ...selectedPart.warnings])),
      },
      setPreviewModels,
    )
    setStatusMessage('Preview model loaded.')
  }, [apiBase, selectedPart, loadStlBuffer])

  const handlePreview = useCallback(async () => {
    if (!draftTransactionToken) return
    setBusy('preview', true)
    try {
      await loadPreviewModel(draftTransactionToken)
    } catch (err) {
      console.error('Failed to load preview model:', err)
      setStatusMessage(`Failed to preview: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy('preview', false)
    }
  }, [draftTransactionToken, loadPreviewModel])

  const handleAccept = useCallback(async () => {
    if (!draftTransactionToken) return

    setBusy('accept', true)
    try {
      const response = await fetch(normalizeDraftEndpoint(apiBase, draftTransactionToken, 'accept'), { method: 'POST' })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }
      const payload = await response.json() as DraftAcceptanceArtifacts
      setAcceptanceArtifacts(payload)
      setStatusMessage(`Draft accepted: ${payload.acceptance_manifest_path}`)
      setPreviewModelPayload(null)
      setPreviewModels([])
      setDraftTransactionToken(null)
      setProposedOperations([])
      setProposalWarnings([])
    } catch (err) {
      console.error('Failed to accept draft:', err)
      setStatusMessage(`Failed to accept draft: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy('accept', false)
    }
  }, [apiBase, draftTransactionToken])

  const handleDiscard = useCallback(async () => {
    if (!draftTransactionToken) return

    setBusy('discard', true)
    try {
      const response = await fetch(apiUrl(apiBase, `/api/draft-transactions/${draftTransactionToken}`), { method: 'DELETE' })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }
      clearDraftState()
      setStatusMessage('Draft transaction discarded.')
    } catch (err) {
      console.error('Failed to discard draft:', err)
      setStatusMessage(`Failed to discard draft: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy('discard', false)
    }
  }, [apiBase, clearDraftState, draftTransactionToken])

  const handleResetCommand = useCallback(() => {
    setPreviewCommand('')
    setProposedOperations([])
    setProposalWarnings([])
  }, [])

  const handleFitToView = useCallback(() => {
    setFitRequest((value) => value + 1)
  }, [])

  const startResizingSource = useCallback((e: ReactPointerEvent) => {
    e.preventDefault()
    setIsResizingSource(true)
    
    const startX = e.clientX
    const startWidth = sourceWidth

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const deltaX = moveEvent.clientX - startX
      const newWidth = Math.max(100, startWidth + deltaX)
      setSourceWidth(newWidth)
    }

    const handlePointerUp = () => {
      setIsResizingSource(false)
      document.removeEventListener('pointermove', handlePointerMove)
      document.removeEventListener('pointerup', handlePointerUp)
      handleFitToView()
    }

    document.addEventListener('pointermove', handlePointerMove)
    document.addEventListener('pointerup', handlePointerUp)
  }, [sourceWidth, handleFitToView])

  const startResizingParts = useCallback((e: ReactPointerEvent) => {
    e.preventDefault()
    setIsResizingParts(true)

    const startX = e.clientX
    const startWidth = partsWidth

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const deltaX = startX - moveEvent.clientX
      const newWidth = Math.max(100, startWidth + deltaX)
      setPartsWidth(newWidth)
    }

    const handlePointerUp = () => {
      setIsResizingParts(false)
      document.removeEventListener('pointermove', handlePointerMove)
      document.removeEventListener('pointerup', handlePointerUp)
      handleFitToView()
    }

    document.addEventListener('pointermove', handlePointerMove)
    document.addEventListener('pointerup', handlePointerUp)
  }, [partsWidth, handleFitToView])

  const handleFrameSelected = useCallback(() => {
    setFrameSelectedRequest((value) => value + 1)
  }, [])

  const handleClearMeasurements = useCallback(() => {
    setClearMeasurementsRequest((value) => value + 1)
  }, [])

  const handleTapeModeChange = useCallback((enabled: boolean) => {
    setTapeMode(enabled)
    if (enabled) {
      setActiveName(null)
    }
  }, [])

  const handlePartActivate = useCallback((partId: string, additive: boolean) => {
    setSelectedIds((prev) => {
      if (!additive) return [partId]
      if (prev.includes(partId)) {
        const remaining = prev.filter((id) => id !== partId)
        return remaining.length ? remaining : [partId]
      }
      return [...prev, partId]
    })
    setActiveName(partId)
  }, [])

  const handleViewerModelActivate = useCallback((partId: string, additive: boolean) => {
    if (additive) {
      handlePartActivate(partId, true)
      return
    }

    setActiveName(partId)
  }, [handlePartActivate])

  const visibleModels = useMemo(
    () => {
      const partById = new Map(viewerParts.map((part) => [part.id, part]))
      const selectedRegistryModels = models
        .filter((model) => selectedIds.includes(model.partId))
        .map((model) => {
          const part = partById.get(model.partId)
          const modelColor = part ? displayColorForPart(part) : model.color
          return {
            ...model,
            color: colorMode === 'model' ? modelColor : WORKBENCH_PART_COLOR,
            wireframeColor: colorMode === 'model' ? MODEL_WIREFRAME_COLOR : WORKBENCH_WIREFRAME_COLOR,
          }
        })

      return [
        ...selectedRegistryModels,
        ...previewModels.map((model) => ({
          ...model,
          color: PREVIEW_MODEL_COLOR,
          wireframeColor: PREVIEW_MODEL_WIREFRAME,
        })),
      ]
    },
    [colorMode, models, previewModels, selectedIds, viewerParts],
  )
  const visibleWarnings = useMemo(
    () => Array.from(new Set(visibleModels.flatMap((model) => model.warnings))).slice(0, 3),
    [visibleModels],
  )
  const visiblePartIds = useMemo(
    () => _uniqueModelPartIds(visibleModels.map((model) => model.partId)),
    [visibleModels],
  )
  const viewportMeasurements = useMemo<ThreadViewportMeasurement[]>(
    () => previewModelPayload?.dimensions
      ? [
          {
            id: `preview-dimensions-${previewModelPayload.transaction_token}`,
            label: 'Draft preview dimensions',
            distance_mm: previewModelPayload.dimensions.length_mm,
            quality_label: previewModelPayload.quality_label,
          },
        ]
      : [],
    [previewModelPayload],
  )
  const buildViewerContextPayload = useCallback((options: { includeViewportScreenshot?: boolean } = {}) => {
    const { includeViewportScreenshot = false } = options
    const capture = captureViewportScreenshot(includeViewportScreenshot ? viewportAnnotations : [])
    return {
      selected_part_ids: selectedIds,
      visible_part_ids: visiblePartIds,
      measurements: viewportMeasurements,
      draft_transaction_token: draftTransactionToken,
      draft_preview_token: null,
      draft_preview_model_url: previewModelPayload?.model_url ?? null,
      draft_preview_available: Boolean(previewModelPayload),
      active_assembly_id: activeAssemblyId ?? previewContext?.active_assembly_id ?? null,
      active_project_revision: backendRevisionRef.current,
      context_note: 'viewport attached from chat',
      viewport_size: capture.viewportSize,
      annotations: viewportAnnotations,
      ...(includeViewportScreenshot ? { viewport_screenshot: capture.screenshot } : {}),
    }
  }, [
    activeAssemblyId,
    draftTransactionToken,
    previewContext,
    previewModelPayload,
    selectedIds,
    viewportAnnotations,
    viewportMeasurements,
    visiblePartIds,
  ])


  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      <Toolbar
        onFitToView={handleFitToView}
        onFrameSelected={handleFrameSelected}
        onReload={() => {
          reloadViewer().catch((err) => {
            console.error('Reload failed:', err)
            setStatusMessage(`Reload failed: ${err.message}`)
          })
        }}
        statusMessage={statusMessage}
        rotationMode={rotationMode}
        onRotationModeChange={setRotationMode}
        tapeMode={tapeMode}
        onTapeModeChange={handleTapeModeChange}
        onClearMeasurements={handleClearMeasurements}
        projectName={projectName}
      />
      <div className="workspace-container">
        <DesignThreadDock
          activeTab={leftDockTab}
          onTabChange={setLeftDockTab}
          sourceContext={sourceContext}
          activePartId={activeName}
          leftDockCollapsed={sourceCollapsed}
          sourceWidth={sourceWidth}
          onToggleLeftDock={() => {
            setSourceCollapsed((value) => !value)
            setTimeout(() => handleFitToView(), 310)
          }}
          leftDockResizing={isResizingSource}
          threads={threadSummaries}
          activeThreadId={activeThreadId}
          activeThread={activeThread}
          threadBusy={threadBusy}
          isThreadMuted={false}
          selectedPartIds={selectedIds}
          visiblePartIds={visiblePartIds}
          activeProjectRevision={backendRevisionRef.current}
          activeAssemblyId={activeAssemblyId ?? previewContext?.active_assembly_id ?? null}
          previewModel={previewModelPayload}
          acceptedArtifacts={acceptanceArtifacts}
          proposalWarnings={proposalWarnings}
          proposedOperations={proposedOperations}
          hasTransaction={Boolean(draftTransactionToken)}
          commandBusy={commandBusy}
          previewContext={previewContext}
          commandText={previewCommand}
          onCommandChange={handlePreviewCommandChange}
          onPropose={handlePropose}
          onApply={handleApply}
          onPreview={handlePreview}
          onAccept={handleAccept}
          onDiscard={handleDiscard}
          onResetCommand={handleResetCommand}
          onCreateThread={createThread}
          onActivateThread={loadThread}
          onPatchThread={patchThread}
          onSendChatMessage={sendThreadChatMessage}
          onCreateViewportAttachment={createViewportAttachment}
          onBuildViewerContext={buildViewerContextPayload}
          threadAttachmentIds={threadAttachmentIds}
          markupActive={markupActive}
          markupTool={markupTool}
          markupNoteText={markupNoteText}
          markupAnnotations={viewportAnnotations}
          onMarkupActiveChange={setMarkupActive}
          onMarkupToolChange={setMarkupTool}
          onMarkupNoteTextChange={setMarkupNoteText}
          onClearMarkup={() => setViewportAnnotations([])}
          onUndoMarkup={() => setViewportAnnotations((current) => current.slice(0, -1))}
        />
        {sourceCollapsed ? null : (
          <div 
            className={`resize-handle left-handle ${isResizingSource ? 'active' : ''}`}
            onPointerDown={startResizingSource}
          />
        )}
        <div className={`workspace-canvas ${isResizingSource || isResizingParts ? 'resizing' : ''}`}>
          <FileDropZone
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onFileSelect={handleFileSelect}
            isDragOver={isDragOver}
          >
            {visibleWarnings.length ? (
              <div className="geometry-warnings" role="status" aria-label="Geometry capability warnings">
                {visibleWarnings.map((warning) => (
                  <div key={warning} className="geometry-warning">{warning}</div>
                ))}
              </div>
            ) : null}
            <Viewer
              models={visibleModels}
              activeName={activeName}
              onActiveNameChange={setActiveName}
              onModelActivate={handleViewerModelActivate}
              fitRequest={fitRequest}
              frameSelectedRequest={frameSelectedRequest}
              rotationMode={rotationMode}
              tapeMode={tapeMode}
              clearMeasurementsRequest={clearMeasurementsRequest}
              onFitToView={handleFitToView}
              onFrameSelected={handleFrameSelected}
              onReload={() => {
                reloadViewer().catch((err) => {
                  console.error('Reload failed:', err)
                  setStatusMessage(`Reload failed: ${err.message}`)
                })
              }}
              onTapeModeChange={handleTapeModeChange}
              onClearMeasurements={handleClearMeasurements}
            />
            <ViewportMarkupOverlay
              active={markupActive}
              tool={markupTool}
              noteText={markupNoteText}
              annotations={viewportAnnotations}
              onChange={setViewportAnnotations}
            />
          </FileDropZone>
        </div>
        {partsCollapsed ? null : (
          <div 
            className={`resize-handle right-handle ${isResizingParts ? 'active' : ''}`}
            onPointerDown={startResizingParts}
          />
        )}
        <ModelList
          parts={viewerParts}
          selectedIds={selectedIds}
          activeId={activeName}
          activeVersion={activeVersion}
          onActivate={handlePartActivate}
          metadataDrafts={partMetadataDrafts}
          onMetadataChange={handlePartMetadataChange}
          onMetadataReset={handlePartMetadataReset}
          colorMode={colorMode}
          onColorModeChange={setColorMode}
          collapsed={partsCollapsed}
          onToggle={() => {
            setPartsCollapsed((value) => !value)
            setTimeout(() => handleFitToView(), 310)
          }}
          width={partsWidth}
          isResizing={isResizingParts}
        />
      </div>
    </div>
  )
}

import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import Viewer from './components/Viewer'
import FileDropZone from './components/FileDropZone'
import ModelList from './components/ModelList'
import Toolbar from './components/Toolbar'
import SourcePanel from './components/SourcePanel'
import EditEntityControls from './components/EditEntityControls'
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
  EditDocumentPayload,
  EditPoint,
  GeometryCapabilities,
  ModelData,
  PartMetadataDraft,
  RotationMode,
  SnapFeature,
  SnapFeaturePayload,
  SourceContext,
  ViewerOccurrence,
  ViewerPart,
  ViewerPartsPayload,
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

function backendBaseUrl() {
  const params = new URLSearchParams(window.location.search)
  return (params.get('api') ?? import.meta.env.VITE_FLOW_CAD_API ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
}

function apiUrl(baseUrl: string, path: string) {
  return new URL(path, `${baseUrl}/`).toString()
}

async function responseDetail(response: Response) {
  try {
    const payload = await response.json()
    return payload.detail ?? `${response.status} ${response.statusText}`
  } catch {
    return `${response.status} ${response.statusText}`
  }
}

interface EditOperationResponse {
  entity?: {
    id?: string
  }
  document?: EditDocumentPayload
}

interface EditPatchResponse {
  document?: EditDocumentPayload
}

interface EditPointResponse {
  point?: {
    id?: string
  }
  document?: EditDocumentPayload
}

interface EditHoleResponse {
  document?: EditDocumentPayload
}

interface EditBooleanResponse {
  document?: EditDocumentPayload
}

interface EditSplitResponse {
  document?: EditDocumentPayload
}

interface EditUndoResponse {
  document?: EditDocumentPayload
}

function isEditComponentId(value: string | null) {
  return Boolean(value?.startsWith('edit:'))
}

function editEntityIdFromComponentId(value: string) {
  return value.replace(/^edit:/, '')
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
  const [colorMode, setColorMode] = useState<ViewerColorMode>('workbench')
  const [partMetadataDrafts, setPartMetadataDrafts] = useState<Record<string, PartMetadataDraft>>({})
  const [editDocument, setEditDocument] = useState<EditDocumentPayload | null>(null)
  const [activePointId, setActivePointId] = useState<string | null>(null)
  const loadingPartIdsRef = useRef<Set<string>>(new Set())

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

    setModels((prev) => {
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
    const previousRevision = backendRevisionRef.current
    if (previousRevision !== null && payload.revision !== previousRevision) {
      setModels((prev) => prev.filter((model) => model.partId.startsWith('file:') || model.partId.startsWith('url:')))
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

  const viewerParts = useMemo(
    () => parts.map((part) => mergePartDraft(part, partMetadataDrafts[part.id])),
    [partMetadataDrafts, parts],
  )

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
    await loadViewerState()
  }, [apiBase, loadViewerState])

  const loadEditDocument = useCallback(async () => {
    const response = await fetch(apiUrl(apiBase, '/api/edit/document'))
    if (!response.ok) {
      throw new Error(await responseDetail(response))
    }
    const payload = await response.json() as EditDocumentPayload
    setEditDocument(payload)
    return payload
  }, [apiBase])

  const handleAddCube = useCallback(async () => {
    setStatusMessage('Adding cube...')
    const response = await fetch(apiUrl(apiBase, '/api/edit/operations'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'create_box' }),
    })
    if (!response.ok) {
      throw new Error(await responseDetail(response))
    }

    const payload = await response.json() as EditOperationResponse
    if (payload.document) {
      setEditDocument(payload.document)
    } else {
      await loadEditDocument()
    }
    await loadViewerState()
    const entityId = payload.entity?.id
    if (entityId) {
      const componentId = `edit:${entityId}`
      setSelectedIds([componentId])
      setActiveName(componentId)
      setTapeMode(false)
      setStatusMessage(`Added ${entityId}`)
    }
  }, [apiBase, loadEditDocument, loadViewerState])

  const undoEditOperation = useCallback(async () => {
    try {
      setStatusMessage('Undoing edit...')
      const response = await fetch(apiUrl(apiBase, '/api/edit/undo'), { method: 'POST' })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }
      const payload = await response.json() as EditUndoResponse
      if (payload.document) {
        setEditDocument(payload.document)
      } else {
        await loadEditDocument()
      }
      await loadViewerState()
      setStatusMessage('Undid edit')
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error('Undo failed:', err)
      setStatusMessage(`Undo failed: ${message}`)
    }
  }, [apiBase, loadEditDocument, loadViewerState])

  const patchEditEntity = useCallback(async (componentId: string, patch: Record<string, unknown>) => {
    const entityId = editEntityIdFromComponentId(componentId)
    try {
      setStatusMessage(`Updating ${entityId}...`)
      const response = await fetch(apiUrl(apiBase, `/api/edit/entities/${encodeURIComponent(componentId)}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }

      const payload = await response.json() as EditPatchResponse
      if (payload.document) {
        setEditDocument(payload.document)
      } else {
        await loadEditDocument()
      }
      await loadViewerState()
      setSelectedIds([componentId])
      setActiveName(componentId)
      setStatusMessage(`Updated ${entityId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error(`Edit update failed for ${entityId}:`, err)
      setStatusMessage(`Update failed: ${message}`)
    }
  }, [apiBase, loadEditDocument, loadViewerState])

  const createEditPoint = useCallback(async (
    positionMm: [number, number, number],
    quality: 'exact' | 'approximate' = 'exact',
    source: Record<string, unknown> = { kind: 'typed_coordinates' },
  ) => {
    try {
      setStatusMessage('Adding point...')
      const response = await fetch(apiUrl(apiBase, '/api/edit/points'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          position_mm: positionMm,
          quality,
          source,
        }),
      })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }

      const payload = await response.json() as EditPointResponse
      if (payload.document) {
        setEditDocument(payload.document)
      } else {
        await loadEditDocument()
      }
      const pointId = payload.point?.id
      if (pointId) {
        setActivePointId(pointId)
        setStatusMessage(`Added ${pointId}`)
      } else {
        setStatusMessage('Added point')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error('Point creation failed:', err)
      setStatusMessage(`Point failed: ${message}`)
    }
  }, [apiBase, loadEditDocument])

  const patchEditPoint = useCallback(async (pointId: string, patch: Record<string, unknown>) => {
    try {
      setStatusMessage(`Updating ${pointId}...`)
      const response = await fetch(apiUrl(apiBase, `/api/edit/points/${encodeURIComponent(pointId)}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }

      const payload = await response.json() as EditPointResponse
      if (payload.document) {
        setEditDocument(payload.document)
      } else {
        await loadEditDocument()
      }
      setActivePointId(pointId)
      setStatusMessage(`Updated ${pointId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error(`Point update failed for ${pointId}:`, err)
      setStatusMessage(`Point update failed: ${message}`)
    }
  }, [apiBase, loadEditDocument])

  const createEditHole = useCallback(async (
    componentId: string,
    pointId: string,
    preset: string,
    axis: [number, number, number],
  ) => {
    const entityId = editEntityIdFromComponentId(componentId)
    try {
      setStatusMessage(`Cutting ${preset} hole in ${entityId}...`)
      const response = await fetch(apiUrl(apiBase, '/api/edit/holes'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_entity_id: componentId,
          point_id: pointId,
          preset,
          axis,
        }),
      })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }

      const payload = await response.json() as EditHoleResponse
      if (payload.document) {
        setEditDocument(payload.document)
      } else {
        await loadEditDocument()
      }
      await loadViewerState()
      setSelectedIds([componentId])
      setActiveName(componentId)
      setActivePointId(pointId)
      setStatusMessage(`Cut ${preset} hole in ${entityId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error(`Hole cut failed for ${entityId}:`, err)
      setStatusMessage(`Hole failed: ${message}`)
    }
  }, [apiBase, loadEditDocument, loadViewerState])

  const createEditBoolean = useCallback(async (
    operation: 'fuse' | 'cut',
    targetComponentId: string,
    toolComponentId: string,
  ) => {
    const targetEntityId = editEntityIdFromComponentId(targetComponentId)
    const toolEntityId = editEntityIdFromComponentId(toolComponentId)
    try {
      setStatusMessage(`${operation === 'fuse' ? 'Fusing' : 'Cutting'} ${targetEntityId} with ${toolEntityId}...`)
      const response = await fetch(apiUrl(apiBase, '/api/edit/booleans'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          operation,
          target_entity_id: targetComponentId,
          tool_entity_id: toolComponentId,
        }),
      })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }

      const payload = await response.json() as EditBooleanResponse
      if (payload.document) {
        setEditDocument(payload.document)
      } else {
        await loadEditDocument()
      }
      await loadViewerState()
      setSelectedIds([targetComponentId])
      setActiveName(targetComponentId)
      setStatusMessage(`${operation === 'fuse' ? 'Fused' : 'Cut'} ${targetEntityId} with ${toolEntityId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error(`Boolean ${operation} failed for ${targetEntityId}:`, err)
      setStatusMessage(`Boolean failed: ${message}`)
    }
  }, [apiBase, loadEditDocument, loadViewerState])

  const createEditSplit = useCallback(async (
    targetComponentId: string,
    axis: [number, number, number],
  ) => {
    const targetEntityId = editEntityIdFromComponentId(targetComponentId)
    try {
      setStatusMessage(`Splitting ${targetEntityId}...`)
      const response = await fetch(apiUrl(apiBase, '/api/edit/splits'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_entity_id: targetComponentId,
          plane_normal: axis,
        }),
      })
      if (!response.ok) {
        throw new Error(await responseDetail(response))
      }

      const payload = await response.json() as EditSplitResponse
      if (payload.document) {
        setEditDocument(payload.document)
      } else {
        await loadEditDocument()
      }
      await loadViewerState()
      setSelectedIds([targetComponentId])
      setActiveName(targetComponentId)
      setStatusMessage(`Split ${targetEntityId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error(`Split failed for ${targetEntityId}:`, err)
      setStatusMessage(`Split failed: ${message}`)
    }
  }, [apiBase, loadEditDocument, loadViewerState])

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
    if (!isEditComponentId(activeName)) return
    loadEditDocument().catch((err) => {
      console.error(`Failed to load edit document for ${activeName}:`, err)
      setStatusMessage(`Edit document unavailable: ${err.message}`)
    })
  }, [activeName, loadEditDocument])

  useEffect(() => {
    if (!editDocument) {
      setActivePointId(null)
      return
    }
    setActivePointId((current) => {
      if (current && editDocument.points[current]) return current
      const firstPointId = Object.keys(editDocument.points)[0] ?? null
      return firstPointId
    })
  }, [editDocument])

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

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    console.log('Drop event on FileDropZone')
    if (e.dataTransfer.files.length) {
      handleFiles(e.dataTransfer.files)
    }
    setIsDragOver(false)
  }, [handleFiles])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      handleFiles(e.target.files)
      e.target.value = ''
    }
  }, [handleFiles])

  const handleFitToView = useCallback(() => {
    setFitRequest((value) => value + 1)
  }, [])

  const startResizingSource = useCallback((e: React.PointerEvent) => {
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

  const startResizingParts = useCallback((e: React.PointerEvent) => {
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
      return models
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
    },
    [colorMode, models, selectedIds, viewerParts],
  )
  const visibleWarnings = useMemo(
    () => Array.from(new Set(visibleModels.flatMap((model) => model.warnings))).slice(0, 3),
    [visibleModels],
  )
  const activeEditEntity = useMemo(() => {
    if (!activeName || !isEditComponentId(activeName) || !editDocument) return null
    const entityId = editEntityIdFromComponentId(activeName)
    const entity = editDocument.entities[entityId]
    return entity ? { componentId: activeName, entityId, entity } : null
  }, [activeName, editDocument])
  const editPoints = useMemo<Record<string, EditPoint>>(() => editDocument?.points ?? {}, [editDocument])
  const booleanToolOptions = useMemo(() => {
    if (!editDocument || !activeEditEntity) return []
    return Object.keys(editDocument.entities)
      .filter((entityId) => entityId !== activeEditEntity.entityId)
      .map((entityId) => ({
        entityId,
        componentId: `edit:${entityId}`,
        label: entityId,
      }))
  }, [activeEditEntity, editDocument])

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
        onAddCube={() => {
          handleAddCube().catch((err) => {
            console.error('Add cube failed:', err)
            setStatusMessage(`Add cube failed: ${err.message}`)
          })
        }}
        onUndo={() => {
          undoEditOperation().catch((err) => {
            console.error('Undo failed:', err)
            setStatusMessage(`Undo failed: ${err.message}`)
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
        <SourcePanel
          context={sourceContext}
          activeId={activeName}
          collapsed={sourceCollapsed}
          onToggle={() => {
            setSourceCollapsed((value) => !value)
            setTimeout(() => handleFitToView(), 310)
          }}
          width={sourceWidth}
          isResizing={isResizingSource}
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
            {activeEditEntity ? (
              <EditEntityControls
                componentId={activeEditEntity.componentId}
                entityId={activeEditEntity.entityId}
                entity={activeEditEntity.entity}
                booleanToolOptions={booleanToolOptions}
                points={editPoints}
                activePointId={activePointId}
                onActivePointChange={setActivePointId}
                onPatch={patchEditEntity}
                onCreatePoint={createEditPoint}
                onPatchPoint={patchEditPoint}
                onCreateHole={createEditHole}
                onCreateBoolean={createEditBoolean}
                onCreateSplit={createEditSplit}
              />
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
              onEditEntityPatch={patchEditEntity}
              onCreateEditPoint={createEditPoint}
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

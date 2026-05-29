import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Box3, Vector3 } from 'three'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import Viewer from './components/Viewer'
import FileDropZone from './components/FileDropZone'
import ModelList from './components/ModelList'
import Toolbar from './components/Toolbar'
import SourcePanel from './components/SourcePanel'
import type { ModelData, RotationMode, SnapFeature, SnapFeaturePayload, SourceContext, ViewerOccurrence, ViewerPart } from './types'

const IDENTITY_OCCURRENCE: ViewerOccurrence = {
  name: 'identity',
  location: [0, 0, 0],
  rotation: [0, 0, 0],
}

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

  const loadStlBuffer = useCallback((
    name: string,
    partId: string,
    occurrences: ViewerOccurrence[],
    content: ArrayBuffer,
    snapFeatures: SnapFeature[] = [],
  ) => {
    const geometry = new STLLoader().parse(content)
    geometry.computeVertexNormals()
    geometry.computeBoundingBox()
    geometry.computeBoundingSphere()

    const box = geometry.boundingBox ?? new Box3().setFromBufferAttribute(geometry.attributes.position)
    const size = box.getSize(new Vector3())
    const center = box.getCenter(new Vector3())

    const model: ModelData = {
      name,
      partId,
      geometry,
      color: '#5ec4ff',
      wireframeColor: '#f4d35e',
      snapFeatures,
      occurrences,
      bounds: {
        min: box.min.clone(),
        max: box.max.clone(),
        size: size.clone(),
        center: center.clone(),
      },
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
    const snapFeatures = await loadSnapFeatures(part)
    loadStlBuffer(part.id, part.id, part.occurrences.length ? part.occurrences : [IDENTITY_OCCURRENCE], content, snapFeatures)
    return part.id
  }, [apiBase, loadSnapFeatures, loadStlBuffer])

  const loadViewerState = useCallback(async () => {
    setStatusMessage('Loading registry parts...')
    const response = await fetch(apiUrl(apiBase, '/api/parts'))
    if (!response.ok) {
      throw new Error(await responseDetail(response))
    }
    const payload = await response.json() as { revision: number; parts: ViewerPart[] }
    backendRevisionRef.current = payload.revision
    setParts(payload.parts)
    setSelectedIds((prev) => {
      const availableIds = new Set(payload.parts.map((part) => part.id))
      const kept = prev.filter((id) => availableIds.has(id))
      if (kept.length) return kept
      const assembledIds = payload.parts.filter((part) => part.default_visible).map((part) => part.id)
      return assembledIds.length ? assembledIds : payload.parts.map((part) => part.id)
    })

    const results = await Promise.allSettled(payload.parts.map((part) => loadPartModel(part)))
    const failures = results.filter((result): result is PromiseRejectedResult => result.status === 'rejected')
    if (failures.length) {
      setStatusMessage(`${payload.parts.length - failures.length}/${payload.parts.length} models loaded; ${failures[0].reason}`)
    } else {
      setStatusMessage(`${payload.parts.length} models loaded`)
    }
    setFitRequest((value) => value + 1)
  }, [apiBase, loadPartModel])

  const reloadViewer = useCallback(async () => {
    setStatusMessage('Reloading viewer...')
    const reloadResponse = await fetch(apiUrl(apiBase, '/api/reload'), { method: 'POST' })
    if (!reloadResponse.ok) {
      throw new Error(await responseDetail(reloadResponse))
    }
    await loadViewerState()
  }, [apiBase, loadViewerState])

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
            backendRevisionRef.current = payload.revision
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

    const part = parts.find((candidate) => candidate.id === activeName)
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
  }, [activeName, apiBase, parts])

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
    () => models.filter((model) => selectedIds.includes(model.partId)),
    [models, selectedIds],
  )

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
      />
      <SourcePanel
        context={sourceContext}
        activeId={activeName}
        collapsed={sourceCollapsed}
        onToggle={() => setSourceCollapsed((value) => !value)}
      />
      <ModelList
        parts={parts}
        selectedIds={selectedIds}
        activeId={activeName}
        onActivate={handlePartActivate}
        collapsed={partsCollapsed}
        onToggle={() => setPartsCollapsed((value) => !value)}
      />
      <FileDropZone
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onFileSelect={handleFileSelect}
        isDragOver={isDragOver}
      >
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
        />
      </FileDropZone>
    </div>
  )
}

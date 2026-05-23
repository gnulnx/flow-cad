import { useEffect, useState, useCallback } from 'react'
import { Box3, Vector3 } from 'three'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import Viewer from './components/Viewer'
import FileDropZone from './components/FileDropZone'
import ModelList from './components/ModelList'
import Toolbar from './components/Toolbar'
import type { ModelData } from './types'

export default function App() {
  const [models, setModels] = useState<ModelData[]>([])
  const [activeName, setActiveName] = useState<string | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [fitRequest, setFitRequest] = useState(0)

  const loadStlBuffer = useCallback((name: string, content: ArrayBuffer) => {
    const geometry = new STLLoader().parse(content)
    geometry.computeVertexNormals()
    geometry.computeBoundingBox()
    geometry.computeBoundingSphere()

    const box = geometry.boundingBox ?? new Box3().setFromBufferAttribute(geometry.attributes.position)
    const size = box.getSize(new Vector3())
    const center = box.getCenter(new Vector3())

    const model: ModelData = {
      name,
      geometry,
      color: '#5ec4ff',
      wireframeColor: '#f4d35e',
      bounds: {
        min: box.min.clone(),
        max: box.max.clone(),
        size: size.clone(),
        center: center.clone(),
      },
    }

    setModels((prev) => {
      const remaining = prev.filter((existing) => existing.name !== name)
      return [...remaining, model]
    })
    setActiveName(name)
    setFitRequest((value) => value + 1)
  }, [])

  const loadStlFile = useCallback((file: File) => {
    const reader = new FileReader()

    reader.onload = (e) => {
      try {
        const content = e.target?.result
        if (!(content instanceof ArrayBuffer)) {
          throw new Error('FileReader did not return STL binary content')
        }
        loadStlBuffer(file.name, content)
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
        loadStlBuffer(requestedStl.split('/').pop() ?? requestedStl, content)
      } catch (err) {
        console.error(`Failed to load ${requestedStl}:`, err)
      }
    }

    void loadRequestedStl()
  }, [loadStlBuffer])

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

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      <Toolbar
        onFitToView={handleFitToView}
      />
      <ModelList models={models} activeName={activeName} onActivate={setActiveName} />
      <FileDropZone
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onFileSelect={handleFileSelect}
        isDragOver={isDragOver}
      >
        <Viewer
          models={models}
          activeName={activeName}
          onActiveNameChange={setActiveName}
          fitRequest={fitRequest}
        />
      </FileDropZone>
    </div>
  )
}

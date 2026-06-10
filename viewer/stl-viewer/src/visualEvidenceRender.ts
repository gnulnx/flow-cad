import * as THREE from 'three'
import type { ModelData, ViewerOccurrence, VisualEvidenceViewPreset } from './types'

const WORLD_UP = new THREE.Vector3(0, 0, 1)
const DEFAULT_WIDTH = 960
const DEFAULT_HEIGHT = 720
const DEFAULT_BACKGROUND = '#080b14'

interface VisualEvidenceRenderOptions {
  models: ModelData[]
  view: VisualEvidenceViewPreset
  width?: number
  height?: number
}

interface VisualEvidenceRenderResult {
  dataUrl: string
  width: number
  height: number
  camera: {
    view: VisualEvidenceViewPreset
    position: [number, number, number]
    target: [number, number, number]
    up: [number, number, number]
  }
  viewport: {
    width: number
    height: number
    render_context: 'offscreen-browser'
  }
}

function occurrenceRotation(occurrence: ViewerOccurrence): [number, number, number] {
  return [
    THREE.MathUtils.degToRad(occurrence.rotation[0]),
    THREE.MathUtils.degToRad(occurrence.rotation[1]),
    THREE.MathUtils.degToRad(occurrence.rotation[2]),
  ]
}

function occurrenceMatrix(occurrence: ViewerOccurrence) {
  const position = new THREE.Vector3(...occurrence.location)
  const rotation = occurrenceRotation(occurrence)
  const quaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(rotation[0], rotation[1], rotation[2]))
  return new THREE.Matrix4().compose(position, quaternion, new THREE.Vector3(1, 1, 1))
}

function boundsForModels(models: ModelData[]) {
  const box = new THREE.Box3()
  let hasBounds = false

  models.forEach((model) => {
    model.geometry.computeBoundingBox()
    const geometryBox = model.geometry.boundingBox
    if (!geometryBox) return

    model.occurrences.forEach((occurrence) => {
      box.union(geometryBox.clone().applyMatrix4(occurrenceMatrix(occurrence)))
      hasBounds = true
    })
  })

  return hasBounds ? box : null
}

export function cameraDirectionForVisualEvidenceView(view: VisualEvidenceViewPreset) {
  switch (view) {
    case 'front':
      return new THREE.Vector3(0, 1, 0)
    case 'back':
      return new THREE.Vector3(0, -1, 0)
    case 'left':
      return new THREE.Vector3(-1, 0, 0)
    case 'right':
      return new THREE.Vector3(1, 0, 0)
    case 'top':
      return new THREE.Vector3(0, 0, 1)
    case 'bottom':
      return new THREE.Vector3(0, 0, -1)
    case 'iso':
    default:
      return new THREE.Vector3(1, 0.9, 0.8).normalize()
  }
}

function cameraUpForVisualEvidenceView(view: VisualEvidenceViewPreset) {
  return view === 'top' || view === 'bottom'
    ? new THREE.Vector3(0, 1, 0)
    : WORLD_UP.clone()
}

function vectorTuple(vector: THREE.Vector3): [number, number, number] {
  return [vector.x, vector.y, vector.z]
}

function fitCameraToBounds(
  camera: THREE.PerspectiveCamera,
  bounds: THREE.Box3,
  view: VisualEvidenceViewPreset,
) {
  const center = bounds.getCenter(new THREE.Vector3())
  const size = bounds.getSize(new THREE.Vector3())
  const radius = Math.max(size.length() / 2, 1)
  const fov = THREE.MathUtils.degToRad(camera.fov)
  const distance = (radius / Math.sin(fov / 2)) * 1.25
  const direction = cameraDirectionForVisualEvidenceView(view)
  const up = cameraUpForVisualEvidenceView(view)

  camera.up.copy(up)
  camera.position.copy(center).addScaledVector(direction, distance)
  camera.near = Math.max(distance / 1000, 0.01)
  camera.far = Math.max(distance * 1000, 2000)
  camera.updateProjectionMatrix()
  camera.lookAt(center)
  camera.updateMatrixWorld()

  return { center, up }
}

function addModelMeshes(scene: THREE.Scene, models: ModelData[]) {
  const disposables: Array<{ dispose: () => void }> = []

  for (const model of models) {
    const material = new THREE.MeshStandardMaterial({
      color: model.color,
      metalness: 0.1,
      roughness: 0.7,
    })
    const edgeGeometry = new THREE.EdgesGeometry(model.geometry, 20)
    const edgeMaterial = new THREE.LineBasicMaterial({ color: model.wireframeColor })
    disposables.push(material, edgeGeometry, edgeMaterial)

    for (const occurrence of model.occurrences) {
      const group = new THREE.Group()
      group.position.set(...occurrence.location)
      group.rotation.set(...occurrenceRotation(occurrence))

      const mesh = new THREE.Mesh(model.geometry, material)
      const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial)
      group.add(mesh)
      group.add(edges)
      scene.add(group)
    }
  }

  return disposables
}

export async function renderVisualEvidenceCapture({
  models,
  view,
  width = DEFAULT_WIDTH,
  height = DEFAULT_HEIGHT,
}: VisualEvidenceRenderOptions): Promise<VisualEvidenceRenderResult> {
  const renderModels = models.filter((model) => model.occurrences.length)
  if (!renderModels.length) {
    throw new Error('No visible models available for visual evidence render')
  }

  const bounds = boundsForModels(renderModels)
  if (!bounds) {
    throw new Error('No model bounds available for visual evidence render')
  }

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height

  let renderer: THREE.WebGLRenderer
  try {
    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      preserveDrawingBuffer: true,
    })
  } catch (error) {
    throw new Error(`Separate render context is unavailable: ${error instanceof Error ? error.message : String(error)}`)
  }

  renderer.setSize(width, height, false)
  renderer.setPixelRatio(1)
  renderer.setClearColor(DEFAULT_BACKGROUND, 1)

  const scene = new THREE.Scene()
  scene.background = new THREE.Color(DEFAULT_BACKGROUND)
  const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 2000)
  const { center, up } = fitCameraToBounds(camera, bounds, view)
  const disposables = addModelMeshes(scene, renderModels)

  scene.add(new THREE.AmbientLight('#ffffff', 1.8))
  const keyLight = new THREE.DirectionalLight('#ffffff', 2.5)
  keyLight.position.copy(camera.position)
  scene.add(keyLight)

  try {
    renderer.render(scene, camera)
    const dataUrl = canvas.toDataURL('image/png')
    return {
      dataUrl,
      width,
      height,
      camera: {
        view,
        position: vectorTuple(camera.position),
        target: vectorTuple(center),
        up: vectorTuple(up),
      },
      viewport: {
        width,
        height,
        render_context: 'offscreen-browser',
      },
    }
  } finally {
    disposables.forEach((disposable) => disposable.dispose())
    renderer.dispose()
  }
}

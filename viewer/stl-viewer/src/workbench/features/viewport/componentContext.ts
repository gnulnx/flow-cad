import * as THREE from 'three'

export interface ComponentContextRequest {
  key: string | null
  clientX: number
  clientY: number
}

/** Open on right-button release, so platforms firing contextmenu on press can still pan. */
export function listenForContextClick(element: HTMLElement, open: (x: number, y: number) => void) {
  let press: { id: number; x: number; y: number; dragged: boolean } | null = null
  const down = (event: PointerEvent) => {
    press = event.button === 2 ? { id: event.pointerId, x: event.clientX, y: event.clientY, dragged: false } : null
  }
  const move = (event: PointerEvent) => {
    if (press && press.id === event.pointerId && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 4) press.dragged = true
  }
  const up = (event: PointerEvent) => {
    const start = press
    if (!start || start.id !== event.pointerId) return
    move(event)
    press = null
    if (event.button === 2 && !start.dragged) open(event.clientX, event.clientY)
  }
  const cancel = () => { press = null }
  const context = (event: MouseEvent) => event.preventDefault()
  element.addEventListener('pointerdown', down)
  element.addEventListener('pointermove', move)
  element.addEventListener('pointerup', up)
  element.addEventListener('pointercancel', cancel)
  element.addEventListener('contextmenu', context)
  window.addEventListener('blur', cancel)
  return () => {
    element.removeEventListener('pointerdown', down)
    element.removeEventListener('pointermove', move)
    element.removeEventListener('pointerup', up)
    element.removeEventListener('pointercancel', cancel)
    element.removeEventListener('contextmenu', context)
    window.removeEventListener('blur', cancel)
  }
}

export function pickContextComponent(scene: THREE.Scene, camera: THREE.Camera, rect: DOMRect, x: number, y: number, keys: ReadonlySet<string>): string | null {
  if (rect.width <= 0 || rect.height <= 0 || x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null
  const targets: THREE.Mesh[] = []
  scene.traverseVisible((object) => {
    if (object instanceof THREE.Mesh && keys.has(object.name)) targets.push(object)
  })
  scene.updateMatrixWorld(true)
  camera.updateMatrixWorld(true)
  const raycaster = new THREE.Raycaster()
  raycaster.setFromCamera(new THREE.Vector2((x - rect.left) / rect.width * 2 - 1, 1 - (y - rect.top) / rect.height * 2), camera)
  return raycaster.intersectObjects(targets, false)[0]?.object.name ?? null
}

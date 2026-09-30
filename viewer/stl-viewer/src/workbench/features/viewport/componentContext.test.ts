import { expect, it, vi } from 'vitest'
import * as THREE from 'three'
import { listenForContextClick, pickContextComponent } from './componentContext'

it('opens after a stationary right release, suppresses native menus, and preserves drag/cancel semantics', () => {
  const element = document.createElement('canvas')
  const open = vi.fn()
  const remove = listenForContextClick(element, open)
  const pointer = (type: string, x: number, button = 2) => element.dispatchEvent(new PointerEvent(type, { pointerId: 1, clientX: x, clientY: 40, button }))
  pointer('pointerdown', 20)
  const context = new MouseEvent('contextmenu', { cancelable: true })
  element.dispatchEvent(context)
  expect(context.defaultPrevented).toBe(true)
  expect(open).not.toHaveBeenCalled()
  pointer('pointerup', 21)
  expect(open).toHaveBeenCalledWith(21, 40)
  open.mockClear()
  pointer('pointerdown', 20)
  pointer('pointermove', 40)
  pointer('pointermove', 20)
  pointer('pointerup', 20)
  expect(open).not.toHaveBeenCalled()
  pointer('pointerdown', 20)
  pointer('pointercancel', 20)
  pointer('pointerup', 20)
  expect(open).not.toHaveBeenCalled()
  pointer('pointerdown', 20, 0)
  pointer('pointerup', 20, 0)
  expect(open).not.toHaveBeenCalled()
  remove()
  pointer('pointerdown', 20)
  pointer('pointerup', 20)
  expect(open).not.toHaveBeenCalled()
})

it('picks the nearest visible component under the cursor, skipping helpers and hidden geometry', () => {
  const camera = new THREE.PerspectiveCamera(45, 1)
  camera.position.set(0, 0, 20)
  camera.lookAt(0, 0, 0)
  const scene = new THREE.Scene()
  const geometry = new THREE.BoxGeometry(4, 4, 1)
  const material = new THREE.MeshBasicMaterial()
  const add = (name: string, z: number) => {
    const mesh = new THREE.Mesh(geometry, material)
    mesh.name = name; mesh.position.z = z; scene.add(mesh)
    return mesh
  }
  const rear = add('rear', 0)
  const front = add('front', 4)
  add('helper', 7)
  const rect = new DOMRect(100, 50, 200, 200)
  const keys = new Set(['front', 'rear'])
  expect(pickContextComponent(scene, camera, rect, 200, 150, keys)).toBe('front')
  front.visible = false
  expect(pickContextComponent(scene, camera, rect, 200, 150, keys)).toBe('rear')
  rear.visible = false
  expect(pickContextComponent(scene, camera, rect, 200, 150, keys)).toBeNull()
  expect(pickContextComponent(scene, camera, rect, 99, 150, keys)).toBeNull()
  geometry.dispose(); material.dispose()
})

import { render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import * as THREE from 'three'
import { NavigationControls } from './NavigationControls'
import { fitFrameToBounds } from './navigation'

const state = vi.hoisted(() => ({ current: {} as Record<string, unknown> }))
vi.mock('@react-three/fiber', () => ({ useThree: () => state.current }))
it('finishes a pending assembly fit as geometry arrives, then preserves the camera on toggles', () => {
  const camera = new THREE.PerspectiveCamera(42)
  state.current = { camera, gl: { domElement: document.createElement('canvas') }, invalidate: vi.fn() }
  const small = { min: [0,0,0] as [number,number,number], max: [10,10,10] as [number,number,number] }
  const full = { min: [-200,-200,0] as [number,number,number], max: [200,200,600] as [number,number,number] }
  const props = { rotationMode: 'turntable' as const, selectedBounds: small, fitRequest: 1,
    frameSelectedRequest: 0, measureMode: false }
  const view = render(<NavigationControls {...props} visibleBounds={small} fittingReady={false} />)
  view.rerender(<NavigationControls {...props} visibleBounds={full} fittingReady />)
  expect(camera.position.toArray()).toEqual(fitFrameToBounds(full,42).position.toArray())
  const fitted = camera.position.clone()
  view.rerender(<NavigationControls {...props} visibleBounds={small} fittingReady />)
  expect(camera.position.toArray()).toEqual(fitted.toArray())
  view.rerender(<NavigationControls {...props} visibleBounds={small} fitRequest={2} fittingReady />)
  expect(camera.position.toArray()).toEqual(fitFrameToBounds(small,42).position.toArray())
})

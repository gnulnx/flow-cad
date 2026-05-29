import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BufferGeometry, Float32BufferAttribute } from 'three'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./components/Viewer', () => ({
  default: () => <div data-testid="viewer">viewer</div>,
}))

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
  parts: [
    {
      id: 'wheel_box_test_body',
      module_id: 'wheel_box',
      filename: 'b3_wheel_box_test_body.step',
      role: 'printable',
      material: 'PETG',
      is_printable: true,
      artifact_format: 'step',
      artifact_path: 'b3/exports/step/wheel_box/b3_wheel_box_test_body.step',
      direct_stl_path: null,
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

function jsonResponse(payload: unknown) {
  return Promise.resolve(new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }))
}

describe('App source loading', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = input.toString()
      if (url.endsWith('/api/parts')) return jsonResponse(partsPayload)
      if (url.endsWith('/api/parts/wheel_box_test_body/source')) return jsonResponse(sourcePayload)
      if (url.endsWith('/api/parts/wheel_box_test_body/snap-features')) {
        return jsonResponse({ component_id: 'wheel_box_test_body', artifact_path: null, source_format: 'step', features: [], warnings: [] })
      }
      if (url.endsWith('/api/parts/wheel_box_test_body/model')) {
        return Promise.resolve(new Response(new ArrayBuffer(8), { status: 200 }))
      }
      if (url.endsWith('/api/health')) return jsonResponse({ revision: 0 })
      return Promise.resolve(new Response('not found', { status: 404 }))
    }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads full source context for the active registry part', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))

    await screen.findByText('src/flow_cad/parts/wheel_box/prototype.py')
    expect(document.querySelector('.source-code')?.textContent).toContain('make_wheel_box_test_body')
    expect(document.querySelector('.source-code')?.textContent).toContain('make_wheel_box_test_top_lid')
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/parts/wheel_box_test_body/source')
    await waitFor(() => expect(screen.getByText('1 models loaded')).toBeInTheDocument())
  })
})

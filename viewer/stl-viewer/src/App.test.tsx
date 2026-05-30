import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BufferGeometry, Float32BufferAttribute } from 'three'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const viewerRenderProps = vi.hoisted(() => [] as Array<{ clearMeasurementsRequest: number; models: Array<Record<string, unknown>> }>)

vi.mock('./components/Viewer', () => ({
  default: (props: { clearMeasurementsRequest: number; models: Array<Record<string, unknown>> }) => {
    viewerRenderProps.push(props)
    return <div data-testid="viewer">viewer</div>
  },
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

function jsonResponse(payload: unknown) {
  return Promise.resolve(new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }))
}

describe('App source loading', () => {
  beforeEach(() => {
    viewerRenderProps.length = 0
    partsRevision = 0
    healthRevision = 0
    activeParts = partsPayload.parts
    snapFeaturesPayload = {
      ...snapFeaturesPayload,
      features: [...snapFeaturesPayload.features],
      warnings: [],
    }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = input.toString()
      if (url.endsWith('/api/parts')) return jsonResponse({ ...partsPayload, revision: partsRevision, parts: activeParts })
      if (url.endsWith('/source')) return jsonResponse(sourcePayload)
      if (url.endsWith('/snap-features')) return jsonResponse(snapFeaturesPayload)
      if (url.endsWith('/model')) {
        return Promise.resolve(new Response(new ArrayBuffer(8), { status: 200 }))
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
})

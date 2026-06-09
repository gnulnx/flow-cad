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
      metadata_status: 'todo',
      metadata_notes: '',
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

const previewContextPayload = {
  component_id: 'wheel_box_test_body',
  module_id: 'wheel_box',
  family: 'wheel_box',
  version: 'b3_v2',
  role: 'printable',
  material: 'PETG',
  artifact_format: 'step',
  artifact_path: 'b3/exports/step/wheel_box/b3_wheel_box_test_body.step',
  source_context_available: true,
  source_url: '/api/parts/wheel_box_test_body/source',
  occurrences: [
    {
      name: 'wheel_box_test_body',
      location: [0, 0, 0],
      rotation: [0, 0, 0],
    },
  ],
  geometry_authority: 'step_kernel',
  quality_label: 'exact',
  capabilities: STEP_CAPABILITIES,
  warnings: [],
  source_measurements: {
    length_mm: 120,
    width_mm: 80,
    height_mm: 40,
    authority: 'step_kernel',
    source: 'part',
  },
  active_assembly_id: 'b3_v2_wheel_box',
  project_frame: {
    units: 'mm',
    origin_mm: [0, 0, 0],
    axes: {
      x_positive: 'right',
      y_positive: 'front',
      z_positive: 'top',
    },
  },
  local_frame: {
    units: 'mm',
    origin_mm: [0, 0, 0],
    rotation_deg: [0, 0, 0],
    axes: {
      x_positive: 'part-local +X',
      y_positive: 'part-local +Y',
      z_positive: 'part-local +Z',
    },
  },
  mating_contracts: {
    available: true,
    relative_path: 'docs/PART_INTERFACES.md',
    summary: 'Project mating-interface contracts live in the project part-interfaces document.',
  },
}

const draftPreviewPayload = {
  transaction_token: 'draft-preview-1',
  part_id: 'wheel_box_test_body',
  model_url: '/api/parts/wheel_box_test_body/preview-model.stl',
  display_stl_path: '/tmp/preview.stl',
  source_step_path: '/tmp/preview.step',
  geometry_authority: 'mesh',
  quality_label: 'approximate',
  facts: ['Preview generated for test'],
  warnings: ['Preview uses approximated geometry'],
  dimensions: {
    length_mm: 120,
    width_mm: 80,
    height_mm: 50,
    authority: 'mesh',
    source: 'preview',
  },
}

const proposalPayload = {
  command: 'Make this a 120 x 45 x 3 mm panel, add two M4 clearance holes 12 mm from the front edge, and put five louvers on the outside face.',
  ok: true,
  part_id: 'wheel_box_test_body',
  operations: [
    {
      name: 'create_box',
      parameters: {
        length: 120,
        width: 45,
        height: 3,
      },
    },
    {
      name: 'add_hole',
      parameters: {
        face: 'top',
        x: 50,
        y: 12,
        diameter: 4,
        through: true,
      },
    },
    {
      name: 'add_hole',
      parameters: {
        face: 'top',
        x: 70,
        y: 12,
        diameter: 4,
        through: true,
      },
    },
    {
      name: 'add_louver_pattern',
      parameters: {
        face: 'top',
        count: 5,
        pitch: 12,
        x: 60,
        y: 22.5,
        width: 10,
        height: 3,
        angle: 0,
      },
    },
  ],
  warnings: ['Outside face is ambiguous without context.'],
  assumptions: ['Assuming outside = top.'],
  errors: [],
}

const draftAcceptPayload = {
  transaction_token: 'draft-preview-1',
  source_patch_path: '/tmp/draft/source.patch',
  generated_source_path: '/tmp/draft/generated.py',
  validator_stub_path: '/tmp/draft/validator.py',
  acceptance_manifest_path: '/tmp/draft/acceptance.json',
  source_loop_commands: ['flow validate run panel-basic --draft-transaction draft-preview-1'],
  source_patch_preview: 'diff --git a/flow/parts/wheel_box_test_body.py b/flow/parts/wheel_box_test_body.py',
  command_source: 'CLI-driven preview transaction',
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

function mockArrayBufferResponse() {
  return Promise.resolve(new Response(new ArrayBuffer(8), { status: 200 }))
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
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = input.toString()
      if (url.endsWith('/api/parts')) return jsonResponse({ ...partsPayload, revision: partsRevision, parts: activeParts })
      if (url.endsWith('/preview-context')) {
        return jsonResponse(previewContextPayload)
      }
      if (url.endsWith('/api/preview-commands/panel')) {
        return jsonResponse(proposalPayload)
      }
      if (url.endsWith('/api/draft-transactions')) {
        if ((init.method ?? 'GET') === 'DELETE') {
          return jsonResponse({})
        }
        return jsonResponse({ transaction_token: draftPreviewPayload.transaction_token })
      }
      const draftTransactionMatch = url.match(/\/api\/draft-transactions\/([^/]+)\/([^/]+)$/)
      if (draftTransactionMatch) {
        const route = draftTransactionMatch[2]
        switch (route) {
          case 'box':
          case 'holes':
          case 'louver-patterns':
          case 'thickness':
            return jsonResponse({})
          case 'preview-model':
            return jsonResponse(draftPreviewPayload)
          case 'accept':
            return jsonResponse(draftAcceptPayload)
          default:
            break
        }
      }
      if (url.includes('/api/draft-transactions/') && init.method === 'DELETE') {
        return jsonResponse({})
      }
      if (url.endsWith('/source')) return jsonResponse(sourcePayload)
      if (url.endsWith('/snap-features')) return jsonResponse(snapFeaturesPayload)
      if (url.endsWith('/model')) {
        return mockArrayBufferResponse()
      }
      if (url.endsWith('/preview-model.stl')) {
        return mockArrayBufferResponse()
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

  it('passes model color mode and part color edits through to viewer models', async () => {
    const user = userEvent.setup()
    render(<App />)

    await vi.waitFor(() => {
      expect(viewerRenderProps.at(-1)?.models[0]?.color).toBe('#8b949e')
    })

    await user.click(screen.getByRole('button', { name: 'Model' }))
    await vi.waitFor(() => {
      expect(viewerRenderProps.at(-1)?.models[0]?.color).toBe('#38bdf8')
    })

    await user.click(screen.getByRole('button', { name: 'Show details for wheel_box_test_body' }))
    await user.clear(screen.getByLabelText('wheel_box_test_body display color'))
    await user.type(screen.getByLabelText('wheel_box_test_body display color'), '#ff0000')

    await vi.waitFor(() => {
      expect(viewerRenderProps.at(-1)?.models[0]?.color).toBe('#ff0000')
    })
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

  it('loads preview context for the active part from backend payload', async () => {
    const user = userEvent.setup()

    render(<App />)
    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))

    await screen.findByText('120 × 80 × 40 mm')
    await screen.findByText('b3_v2_wheel_box')
    await screen.findByText('docs/PART_INTERFACES.md')
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/parts/wheel_box_test_body/preview-context')
  })

  it('builds a deterministic proposal from command input', async () => {
    const user = userEvent.setup()

    render(<App />)
    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))

    await user.type(screen.getByLabelText('Command'), proposalPayload.command)
    await user.click(screen.getByRole('button', { name: 'Propose' }))

    await screen.findByText('box: resize base panel to 120 x 45 x 3 mm')
    expect(await screen.findAllByText('holes: add 4 mm clearance hole on top')).toHaveLength(2)
    await screen.findByText('louver-patterns: add 5 louver pattern on top')
    await screen.findByText('Outside face is ambiguous without context.')
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/preview-commands/panel', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        command: proposalPayload.command,
        part_id: 'wheel_box_test_body',
      }),
    }))
    expect(screen.queryByText(/Unsupported command/)).not.toBeInTheDocument()
  })

  it('loads a preview model and forwards it to viewer as draft geometry', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await user.type(screen.getByLabelText('Command'), 'Make this a 120 x 45 x 3 mm panel')

    await user.click(screen.getByRole('button', { name: 'Propose' }))
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await user.click(screen.getByRole('button', { name: 'Preview' }))

    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      const previewModel = latestModels.find((model) => model.partId === 'draft:draft-preview-1') as { color?: string } | undefined
      expect(previewModel?.color).toBe('#f97316')
    })

    expect(screen.getByText('/api/parts/wheel_box_test_body/preview-model.stl')).toBeInTheDocument()
    expect(screen.getByText('120 × 80 × 50 mm')).toBeInTheDocument()
    expect(screen.getByText('+0 × +0 × +10 mm')).toBeInTheDocument()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/draft-transactions/draft-preview-1/preview-model', {
      method: 'POST',
    })
  })

  it('clears draft preview state on discard and accept', async () => {
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByText('wheel_box_test_body'))
    await user.type(screen.getByLabelText('Command'), 'Make this a 120 x 45 x 3 mm panel')
    await user.click(screen.getByRole('button', { name: 'Propose' }))
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await user.click(screen.getByRole('button', { name: 'Preview' }))

    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(true)
    })

    await user.click(screen.getByRole('button', { name: 'Discard' }))

    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(false)
    })

    await waitFor(() => {
      expect(screen.getByText('No preview generated yet.')).toBeInTheDocument()
    })

    await user.clear(screen.getByLabelText('Command'))
    await user.type(screen.getByLabelText('Command'), 'Make this a 120 x 45 x 3 mm panel')
    await user.click(screen.getByRole('button', { name: 'Propose' }))

    // Rebuild and accept to verify accept also clears draft geometry.
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await user.click(screen.getByRole('button', { name: 'Preview' }))
    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(true)
    })

    await user.click(screen.getByRole('button', { name: 'Accept' }))
    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'draft:draft-preview-1')).toBe(false)
      expect(screen.getByText('/tmp/draft/acceptance.json')).toBeInTheDocument()
      expect(screen.getByText('flow validate run panel-basic --draft-transaction draft-preview-1')).toBeInTheDocument()
      expect(screen.getByText(/diff --git a\/flow\/parts\/wheel_box_test_body.py/)).toBeInTheDocument()
    })
  })
})

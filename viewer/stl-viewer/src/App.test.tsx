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

const EDIT_CAPABILITIES = {
  ...STEP_CAPABILITIES,
  exact_editing: true,
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

const editBoxPart = {
  id: 'edit:box_001',
  module_id: 'flow_document',
  version: '',
  family: 'flow_document',
  assembly_ids: [],
  compatible_versions: [],
  filename: 'box_001.step',
  role: 'inspection',
  material: '',
  mass_kg: null,
  center_of_mass_mm: null,
  inertia_kg_m2: null,
  mass_source: 'unset',
  is_printable: false,
  artifact_format: 'step',
  artifact_path: 'example/viewer-cache/edit-step/box_001.step',
  direct_stl_path: null,
  source_kind: 'flow_document',
  geometry_authority: 'step_kernel',
  quality_label: 'exact',
  capabilities: EDIT_CAPABILITIES,
  warnings: [],
  model_url: '/api/parts/edit:box_001/model',
  source_url: '/api/parts/edit:box_001/source',
  snap_features_url: '/api/parts/edit:box_001/snap-features',
  occurrences: [
    {
      name: 'box_001',
      location: [0, 0, 0],
      rotation: [0, 0, 0],
    },
  ],
  in_assembly: false,
  default_visible: true,
}

const editToolPart = {
  ...editBoxPart,
  id: 'edit:tool',
  filename: 'tool.step',
  artifact_path: 'example/viewer-cache/edit-step/tool.step',
  model_url: '/api/parts/edit:tool/model',
  source_url: '/api/parts/edit:tool/source',
  snap_features_url: '/api/parts/edit:tool/snap-features',
  occurrences: [
    {
      name: 'tool',
      location: [0, 0, 0],
      rotation: [0, 0, 0],
    },
  ],
}

let editPoints: Record<string, {
  position_mm: [number, number, number]
  coordinate_space: string
  quality: 'exact' | 'approximate'
  source: Record<string, unknown>
}> = {}
let editBoxHoles: Array<Record<string, unknown>> = []
let editBoxBooleans: Array<Record<string, unknown>> = []
let editBoxAvailable = false
let editToolAvailable = false

function editDocumentPayload() {
  const entities: Record<string, {
    kind: string
    name: string
    size_mm: number[]
    transform: {
      translation_mm: number[]
      rotation_deg: number[]
    }
    role: string
    holes: Array<Record<string, unknown>>
    booleans: Array<Record<string, unknown>>
  }> = {}
  if (editBoxAvailable) {
    entities.box_001 = {
      kind: 'primitive_box',
      name: 'box_001',
      size_mm: [20, 20, 20],
      transform: {
        translation_mm: [0, 0, 0],
        rotation_deg: [0, 0, 0],
      },
      role: 'inspection',
      holes: editBoxHoles,
      booleans: editBoxBooleans,
    }
  }
  if (editToolAvailable) {
    entities.tool = {
      kind: 'primitive_box',
      name: 'tool',
      size_mm: [10, 10, 10],
      transform: {
        translation_mm: [0, 0, 0],
        rotation_deg: [0, 0, 0],
      },
      role: 'inspection',
      holes: [],
      booleans: [],
    }
  }
  return {
    schema_version: 1,
    document_id: 'main',
    units: 'mm',
    revision: partsRevision,
    document_path: 'flow/document.json',
    entities,
    points: editPoints,
    operations: [],
  }
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
    editPoints = {}
    editBoxHoles = []
    editBoxBooleans = []
    editBoxAvailable = false
    editToolAvailable = false
    snapFeaturesPayload = {
      ...snapFeaturesPayload,
      features: [...snapFeaturesPayload.features],
      warnings: [],
    }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString()
      if (url.endsWith('/api/parts')) return jsonResponse({ ...partsPayload, revision: partsRevision, parts: activeParts })
      if (url.endsWith('/api/edit/operations')) {
        partsRevision += 1
        healthRevision = partsRevision
        editBoxAvailable = true
        activeParts = [...partsPayload.parts, editBoxPart]
        return jsonResponse({ ok: true, document_revision: partsRevision, entity: { id: 'box_001' }, document: editDocumentPayload() })
      }
      if (url.endsWith('/api/edit/document')) return jsonResponse(editDocumentPayload())
      if (url.endsWith('/api/edit/points') && init?.method === 'POST') {
        partsRevision += 1
        healthRevision = partsRevision
        const payload = JSON.parse(String(init?.body ?? '{}'))
        editPoints = {
          ...editPoints,
          point_001: {
            position_mm: payload.position_mm,
            coordinate_space: payload.coordinate_space ?? 'world',
            quality: payload.quality ?? 'exact',
            source: payload.source ?? {},
          },
        }
        return jsonResponse({ ok: true, document_revision: partsRevision, point: { id: 'point_001' }, document: editDocumentPayload() })
      }
      if (url.includes('/api/edit/points/') && init?.method === 'PATCH') {
        partsRevision += 1
        healthRevision = partsRevision
        const pointId = decodeURIComponent(url.split('/').pop() ?? '')
        const payload = JSON.parse(String(init?.body ?? '{}'))
        editPoints = {
          ...editPoints,
          [pointId]: {
            ...(editPoints[pointId] ?? { position_mm: [0, 0, 0], coordinate_space: 'world', quality: 'exact', source: {} }),
            ...payload,
          },
        }
        return jsonResponse({ ok: true, document_revision: partsRevision, point: { id: pointId }, document: editDocumentPayload() })
      }
      if (url.endsWith('/api/edit/holes') && init?.method === 'POST') {
        partsRevision += 1
        healthRevision = partsRevision
        editBoxAvailable = true
        const payload = JSON.parse(String(init?.body ?? '{}'))
        editBoxHoles = [
          ...editBoxHoles,
          {
            id: 'hole_001',
            point_id: payload.point_id,
            position_mm: editPoints[payload.point_id]?.position_mm ?? [0, 0, 0],
            axis: payload.axis,
            preset: payload.preset,
            diameter_mm: payload.preset === 'm5_clearance' ? 5.5 : 4.5,
            through: true,
          },
        ]
        activeParts = [...partsPayload.parts, editBoxPart]
        return jsonResponse({ ok: true, document_revision: partsRevision, hole: editBoxHoles.at(-1), document: editDocumentPayload() })
      }
      if (url.endsWith('/api/edit/booleans') && init?.method === 'POST') {
        partsRevision += 1
        healthRevision = partsRevision
        editBoxAvailable = true
        const payload = JSON.parse(String(init?.body ?? '{}'))
        editBoxBooleans = [
          ...editBoxBooleans,
          {
            id: 'boolean_001',
            type: payload.operation,
            tool_entity_id: 'tool',
            keep_tool: true,
          },
        ]
        editToolAvailable = true
        activeParts = [...partsPayload.parts, editBoxPart, editToolPart]
        return jsonResponse({ ok: true, document_revision: partsRevision, boolean: editBoxBooleans.at(-1), document: editDocumentPayload() })
      }
      if (url.endsWith('/api/edit/splits') && init?.method === 'POST') {
        partsRevision += 1
        healthRevision = partsRevision
        editBoxAvailable = true
        activeParts = [...partsPayload.parts, editBoxPart]
        return jsonResponse({ ok: true, document_revision: partsRevision, document: editDocumentPayload() })
      }
      if (url.endsWith('/api/edit/undo') && init?.method === 'POST') {
        partsRevision += 1
        healthRevision = partsRevision
        editBoxAvailable = false
        editToolAvailable = false
        editPoints = {}
        editBoxHoles = []
        editBoxBooleans = []
        activeParts = partsPayload.parts
        return jsonResponse({ ok: true, document_revision: partsRevision, document: editDocumentPayload() })
      }
      if (url.includes('/api/edit/entities/')) {
        partsRevision += 1
        healthRevision = partsRevision
        const patch = JSON.parse(String(init?.body ?? '{}'))
        const document = editDocumentPayload()
        document.revision = partsRevision
        if (Array.isArray(patch.translation_mm)) {
          document.entities.box_001.transform.translation_mm = patch.translation_mm
        }
        if (Array.isArray(patch.size_mm)) {
          document.entities.box_001.size_mm = patch.size_mm
        }
        return jsonResponse({ ok: true, document_revision: partsRevision, entity: { id: 'box_001' }, document })
      }
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

  it('creates a cube edit operation and selects the returned edit entity', async () => {
    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByRole('button', { name: 'Cube' }))

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/edit/operations',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ type: 'create_box' }),
        }),
      )
    })
    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'edit:box_001')).toBe(true)
    })
  })

  it('undoes the last edit operation from the toolbar', async () => {
    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByRole('button', { name: 'Cube' }))
    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'edit:box_001')).toBe(true)
    })
    await user.click(screen.getByRole('button', { name: 'Undo' }))

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/edit/undo',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    await waitFor(() => {
      const latestModels = viewerRenderProps.at(-1)?.models ?? []
      expect(latestModels.some((model) => model.partId === 'edit:box_001')).toBe(false)
    })
  })

  it('patches selected cube center and size from exact edit controls', async () => {
    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByRole('button', { name: 'Cube' }))

    const centerX = await screen.findByLabelText('box_001 center X')
    await user.clear(centerX)
    await user.type(centerX, '5')
    await user.click(screen.getByRole('button', { name: 'Apply Center' }))

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/edit/entities/edit%3Abox_001',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ translation_mm: [5, 0, 0] }),
        }),
      )
    })

    const sizeX = await screen.findByLabelText('box_001 size X')
    await user.clear(sizeX)
    await user.type(sizeX, '30')
    await user.click(screen.getByRole('button', { name: 'Apply Size' }))

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/edit/entities/edit%3Abox_001',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ size_mm: [30, 20, 20] }),
        }),
      )
    })
  })

  it('creates an exact point and cuts a preset through-hole in the active edit entity', async () => {
    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.click(screen.getByRole('button', { name: 'Cube' }))

    await user.clear(await screen.findByLabelText('new point X'))
    await user.type(screen.getByLabelText('new point X'), '1')
    await user.clear(screen.getByLabelText('new point Y'))
    await user.type(screen.getByLabelText('new point Y'), '2')
    await user.clear(screen.getByLabelText('new point Z'))
    await user.type(screen.getByLabelText('new point Z'), '3')
    await user.click(screen.getByRole('button', { name: 'Add Point' }))

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/edit/points',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            position_mm: [1, 2, 3],
            quality: 'exact',
            source: { kind: 'typed_coordinates' },
          }),
        }),
      )
    })

    await user.selectOptions(screen.getByLabelText('box_001 hole preset'), 'm5_clearance')
    await user.click(screen.getByRole('button', { name: 'Cut Through Hole' }))

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/edit/holes',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            target_entity_id: 'edit:box_001',
            point_id: 'point_001',
            preset: 'm5_clearance',
            axis: [0, 0, 1],
          }),
        }),
      )
    })
  })

  it('applies a boolean cut from the active edit entity controls', async () => {
    const user = userEvent.setup()
    editBoxAvailable = true
    editToolAvailable = true
    activeParts = [...partsPayload.parts, editBoxPart, editToolPart]
    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.selectOptions(screen.getByLabelText('Version filter'), '__all__')
    await user.click(screen.getByRole('button', { name: 'Inspect' }))
    await user.click(await screen.findByText('edit:box_001'))

    await user.selectOptions(await screen.findByLabelText('box_001 boolean tool'), 'edit:tool')
    await user.click(screen.getByRole('button', { name: 'Cut Body' }))

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/edit/booleans',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            operation: 'cut',
            target_entity_id: 'edit:box_001',
            tool_entity_id: 'edit:tool',
          }),
        }),
      )
    })
  })

  it('applies a plane split from the active edit entity controls', async () => {
    const user = userEvent.setup()
    editBoxAvailable = true
    activeParts = [...partsPayload.parts, editBoxPart]
    render(<App />)

    await screen.findByText('wheel_box_test_body')
    await user.selectOptions(screen.getByLabelText('Version filter'), '__all__')
    await user.click(screen.getByRole('button', { name: 'Inspect' }))
    await user.click(await screen.findByText('edit:box_001'))

    await user.selectOptions(await screen.findByLabelText('box_001 split axis'), 'x')
    await user.click(screen.getByRole('button', { name: 'Split Body' }))

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/edit/splits',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            target_entity_id: 'edit:box_001',
            plane_normal: [1, 0, 0],
          }),
        }),
      )
    })
  })
})

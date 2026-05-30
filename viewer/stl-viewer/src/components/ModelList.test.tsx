import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ModelList from './ModelList'
import type { GeometryCapabilities, ViewerPart } from '../types'

const STEP_CAPABILITIES: GeometryCapabilities = {
  display_mesh: true,
  mesh_metrics: true,
  exact_topology: true,
  exact_snap: true,
  exact_measurement: true,
  approximate_measurement: false,
  exact_editing: false,
  mesh_only: false,
}

function part(
  id: string,
  moduleId = 'wheel_box',
  overrides: Partial<ViewerPart> = {},
): ViewerPart {
  return {
    id,
    module_id: moduleId,
    version: 'b3_v2',
    family: moduleId,
    assembly_ids: ['b3_v2_wheel_box'],
    compatible_versions: [],
    filename: `${id}.step`,
    role: 'printable',
    material: 'PETG',
    mass_kg: null,
    center_of_mass_mm: null,
    inertia_kg_m2: null,
    mass_source: 'unset',
    is_printable: true,
    artifact_format: 'step',
    artifact_path: `b3/exports/step/b3_v2/${moduleId}/${id}.step`,
    direct_stl_path: null,
    source_kind: 'flow_python',
    geometry_authority: 'step_kernel',
    quality_label: 'exact',
    capabilities: STEP_CAPABILITIES,
    warnings: [],
    model_url: `/api/parts/${id}/model`,
    source_url: `/api/parts/${id}/source`,
    occurrences: [
      {
        name: id,
        location: [0, 0, 0],
        rotation: [0, 0, 0],
      },
    ],
    in_assembly: true,
    default_visible: false,
    ...overrides,
  }
}

describe('ModelList', () => {
  it('activates a part and passes additive intent from ctrl/meta clicks', async () => {
    const user = userEvent.setup()
    const onActivate = vi.fn()

    render(
      <ModelList
        parts={[part('wheel_box_test_body'), part('wheel_box_tight_insert')]}
        selectedIds={['wheel_box_test_body']}
        activeId="wheel_box_test_body"
        activeVersion="b3_v2"
        onActivate={onActivate}
        collapsed={false}
        onToggle={vi.fn()}
      />,
    )

    await user.click(screen.getByText('wheel_box_tight_insert'))
    await user.keyboard('{Control>}')
    await user.click(screen.getByText('wheel_box_test_body'))
    await user.keyboard('{/Control}')

    expect(onActivate).toHaveBeenNthCalledWith(1, 'wheel_box_tight_insert', false)
    expect(onActivate).toHaveBeenNthCalledWith(2, 'wheel_box_test_body', true)
  })

  it('keeps only the header visible when collapsed', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()

    render(
      <ModelList
        parts={[part('wheel_box_test_body')]}
        selectedIds={[]}
        activeId={null}
        activeVersion="b3_v2"
        onActivate={vi.fn()}
        collapsed={true}
        onToggle={onToggle}
      />,
    )

    expect(screen.getByRole('button', { name: 'Parts' })).toBeInTheDocument()
    expect(screen.queryByText('wheel_box_test_body')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Parts' }))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('groups the menu by active version, role, and family while hiding legacy by default', () => {
    render(
      <ModelList
        parts={[
          part('wheel_box_test_body'),
          part('reference_wheel_pair', 'reference', {
            role: 'reference',
            is_printable: false,
            family: 'reference',
            default_visible: false,
          }),
          part('left_side_plate', 'lower_chassis', {
            version: 'b3_v1',
            family: 'lower_chassis',
            role: 'legacy',
            is_printable: false,
            default_visible: false,
            assembly_ids: ['b3_v1_lower_chassis'],
          }),
        ]}
        selectedIds={[]}
        activeId={null}
        activeVersion="b3_v2"
        onActivate={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />,
    )

    expect(screen.getAllByText('b3_v2').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Printable').length).toBeGreaterThan(0)
    expect(screen.getByText('wheel_box')).toBeInTheDocument()
    expect(screen.getByText('wheel_box_test_body')).toBeInTheDocument()
    expect(screen.queryByText('left_side_plate')).not.toBeInTheDocument()
    expect(screen.queryByText('reference_wheel_pair')).not.toBeInTheDocument()
  })

  it('can reveal older versions and hidden roles', async () => {
    const user = userEvent.setup()

    render(
      <ModelList
        parts={[
          part('wheel_box_test_body'),
          part('left_side_plate', 'lower_chassis', {
            version: 'b3_v1',
            family: 'lower_chassis',
            role: 'legacy',
            is_printable: false,
            default_visible: false,
            assembly_ids: ['b3_v1_lower_chassis'],
          }),
        ]}
        selectedIds={[]}
        activeId={null}
        activeVersion="b3_v2"
        onActivate={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />,
    )

    await user.selectOptions(screen.getByLabelText('Version filter'), 'b3_v1')
    expect(screen.queryByText('left_side_plate')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Legacy' }))
    expect(screen.getByText('left_side_plate')).toBeInTheDocument()
  })
})

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { createTestWorkbenchClient } from '../../testClient'
import { PartInventoryDock } from './PartInventoryDock'

function part(authorityHash: string): WorkbenchPart {
  return {
    uuid: 'guard-uuid', key: 'arch_guard', aliases: [], role: 'printable', status: 'active', artifactState: 'indexed',
    geometryAuthority: 'step', qualityLabel: 'Exact', occurrenceCount: 1, occurrenceIds: ['guard-main'], occurrences: [],
    authorityHash, displayArtifact: null, bounds: null, warnings: [],
  }
}

describe('PartInventoryDock refresh', () => {
  it('does not refetch when inventory delivery changes parent callback identities', async () => {
    const client = createTestWorkbenchClient()
    client.getInventory = vi.fn().mockResolvedValue({ revision: 1, activeAssemblyId: 'active', parts: [part('sha')] })
    const firstSelect = vi.fn()
    const view = render(<PartInventoryDock client={client} activePartUuid="guard-uuid" onSelect={firstSelect} onInventoryChange={vi.fn()} />)
    await waitFor(() => expect(firstSelect).toHaveBeenCalledOnce())
    const nextSelect = vi.fn()
    view.rerender(<PartInventoryDock client={client} activePartUuid="guard-uuid" onSelect={nextSelect} onInventoryChange={vi.fn()} />)
    await waitFor(() => expect(client.getInventory).toHaveBeenCalledTimes(1))
    expect(nextSelect).not.toHaveBeenCalled()
    view.rerender(<PartInventoryDock client={client} activePartUuid="guard-uuid" onSelect={nextSelect} refreshToken={1} />)
    await waitFor(() => expect(nextSelect).toHaveBeenCalledWith(expect.objectContaining({ authorityHash: 'sha' }), 'focus'))
    expect(client.getInventory).toHaveBeenCalledTimes(2)
  })

  it('initially focuses an active assembly occurrence before unplaced references', async () => {
    const reference = { ...part('old'), uuid: 'reference', key: 'aaa_reference' }
    const assembly = { ...part('new'), uuid: 'robot', key: 'robot', occurrences: [
      { id: 'robot-main', assemblyId: 'active', translationMm: [0, 0, 0], rotationDeg: [0, 0, 0] },
    ] } as WorkbenchPart
    const client = createTestWorkbenchClient({ inventory: { revision: 1, activeAssemblyId: 'active', parts: [reference, assembly] } })
    const onSelect = vi.fn()
    render(<PartInventoryDock client={client} activePartUuid={null} onSelect={onSelect} />)
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ uuid: 'robot' }), 'focus'))
  })

  it('rebinds the current selection to refreshed artifact metadata', async () => {
    const getInventory = vi.fn()
      .mockResolvedValueOnce({ revision: 1, activeAssemblyId: 'active', parts: [part('old-sha')] })
      .mockResolvedValueOnce({ revision: 2, activeAssemblyId: 'active', parts: [part('new-sha')] })
    const client = createTestWorkbenchClient()
    client.getInventory = getInventory
    const onSelect = vi.fn()
    const view = render(<PartInventoryDock client={client} activePartUuid="guard-uuid" visiblePartUuids={['guard-uuid']} onSelect={onSelect} refreshToken={0} />)
    await waitFor(() => expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ authorityHash: 'old-sha' }), 'focus'))

    view.rerender(<PartInventoryDock client={client} activePartUuid="guard-uuid" visiblePartUuids={['guard-uuid']} onSelect={onSelect} refreshToken={1} />)
    await waitFor(() => expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ authorityHash: 'new-sha' }), 'focus'))
  })

  it('emits replace for click and toggle for Ctrl or Command click', async () => {
    const user = userEvent.setup()
    const client = createTestWorkbenchClient({ inventory: { revision: 1, activeAssemblyId: 'active', parts: [part('sha')] } })
    const onSelect = vi.fn()
    render(<PartInventoryDock client={client} activePartUuid={null} visiblePartUuids={[]} onSelect={onSelect} />)
    const option = await screen.findByRole('option', { name: /arch_guard/ })
    onSelect.mockClear()

    await user.click(option)
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ uuid: 'guard-uuid' }), 'replace')
    await user.keyboard('{Control>}')
    await user.click(option)
    await user.keyboard('{/Control}')
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ uuid: 'guard-uuid' }), 'toggle')
  })

  it('exposes an explicit visibility toggle independent of row selection', async () => {
    const user = userEvent.setup()
    const active = { ...part('sha'), family: 'compute', material: 'PETG' }
    const client = createTestWorkbenchClient({ inventory: { revision: 1, activeAssemblyId: 'active', parts: [active] } })
    const onSelect = vi.fn()
    render(<PartInventoryDock client={client} activePartUuid={null} visiblePartUuids={['guard-uuid']} onSelect={onSelect} />)

    expect(await screen.findByRole('group', { name: 'compute parts' })).toBeInTheDocument()
    expect(screen.getByText(/active · PETG/)).toBeInTheDocument()
    onSelect.mockClear()
    await user.click(screen.getByRole('button', { name: 'Hide arch_guard' }))
    expect(onSelect).toHaveBeenCalledOnce()
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ uuid: 'guard-uuid' }), 'toggle')
  })

  it('collapses sections without changing visibility and reveals search matches', async () => {
    const user = userEvent.setup()
    const guard = { ...part('sha'), family: 'head' }
    const wheel = { ...part('wheel'), uuid: 'wheel', key: 'wheel', family: 'drive_train' }
    const client = createTestWorkbenchClient({ inventory: { revision: 1, activeAssemblyId: 'active', parts: [guard, wheel] } })
    const onSelect = vi.fn()
    render(<PartInventoryDock client={client} activePartUuid="guard-uuid" visiblePartUuids={['guard-uuid']} onSelect={onSelect} />)
    await screen.findByRole('group', { name: 'head parts' })
    onSelect.mockClear()
    expect(screen.getAllByRole('option').filter((node) => node.tagName === 'BUTTON')).toHaveLength(2)
    await user.click(screen.getByRole('button', { name: 'Collapse all' }))
    expect(screen.queryByRole('option', { name: /arch_guard|wheel/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /head.*1 parts/ }))
    expect(screen.getByRole('button', { name: 'Hide arch_guard' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Collapse all' }))
    expect(screen.queryByRole('option', { name: /arch_guard|wheel/ })).not.toBeInTheDocument()
    expect(onSelect).not.toHaveBeenCalled()
    await user.type(screen.getByRole('searchbox'), 'drive train')
    expect(screen.getByRole('option', { name: /wheel/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /arch_guard/ })).not.toBeInTheDocument()
    await user.clear(screen.getByRole('searchbox'))
    await user.click(screen.getByRole('button', { name: 'Expand all' }))
    expect(screen.getAllByRole('option').filter((node) => node.tagName === 'BUTTON')).toHaveLength(2)
  })
  it('defaults to make, filters by category and material without changing the scene, and searches every field', async () => {
    const user = userEvent.setup()
    const parts: WorkbenchPart[] = [
      { ...part('sha'), category: 'make', displayName: 'Arch guard', material: 'PETG', family: 'head' },
      { ...part('motor'), uuid: 'motor', key: 'motor', category: 'purchased', displayName: 'Wheel motor' },
      { ...part('screw'), uuid: 'screw', key: 'm3_screw', category: 'hardware', material: 'Steel' },
      { ...part('bumper'), uuid: 'bumper', key: 'bumper', category: 'make', material: 'TPU', family: 'head' },
      { ...part('view'), uuid: 'view', key: 'robot_open', category: 'view' },
      { ...part('unknown'), uuid: 'unknown', key: 'uncategorized', role: 'inspection' },
    ]
    const onSelect = vi.fn()
    const client = createTestWorkbenchClient({ inventory: { revision: 1, activeAssemblyId: 'active', parts } })
    render(<PartInventoryDock client={client} activePartUuid="guard-uuid" visiblePartUuids={['guard-uuid', 'motor']} onSelect={onSelect} />)
    await screen.findByRole('option', { name: /Arch guard/ })
    onSelect.mockClear()
    const rows = () => screen.getAllByRole('option').filter((node) => node.tagName === 'BUTTON')
    expect(rows()).toHaveLength(2)
    expect(screen.getByRole('tab', { name: /Parts to make/ })).toHaveAttribute('aria-selected', 'true')
    await user.selectOptions(screen.getByLabelText('Filter by material'), 'PETG')
    expect(rows()).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Hide Arch guard' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /Purchased/ }))
    expect(screen.getByRole('button', { name: 'Hide Wheel motor' })).toBeInTheDocument()
    expect(screen.getByLabelText('Filter by material')).toHaveValue('')
    await user.click(screen.getByRole('tab', { name: /Hardware/ }))
    expect(rows()).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Show m3_screw' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /^All/ }))
    expect(rows()).toHaveLength(6)
    await user.type(screen.getByRole('searchbox'), 'head PETG')
    expect(rows()).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Hide Arch guard' })).toBeInTheDocument()
    expect(onSelect).not.toHaveBeenCalled()
    await user.clear(screen.getByRole('searchbox'))
    await user.click(screen.getByRole('tab', { name: /Views/ }))
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: /References/ })).toHaveAttribute('aria-selected', 'true')
  })

})

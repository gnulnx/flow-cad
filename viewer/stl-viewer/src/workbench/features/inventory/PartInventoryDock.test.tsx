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
    expect(screen.getByText(/printable · active · PETG/)).toBeInTheDocument()
    onSelect.mockClear()
    await user.click(screen.getByRole('button', { name: 'Hide arch_guard' }))
    expect(onSelect).toHaveBeenCalledOnce()
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ uuid: 'guard-uuid' }), 'toggle')
  })
})

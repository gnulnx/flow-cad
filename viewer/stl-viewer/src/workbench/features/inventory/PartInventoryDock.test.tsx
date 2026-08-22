import { render, waitFor } from '@testing-library/react'
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
    const view = render(<PartInventoryDock client={client} activePartUuid="guard-uuid" onSelect={onSelect} refreshToken={0} />)
    await waitFor(() => expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ authorityHash: 'old-sha' })))

    view.rerender(<PartInventoryDock client={client} activePartUuid="guard-uuid" onSelect={onSelect} refreshToken={1} />)
    await waitFor(() => expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ authorityHash: 'new-sha' })))
  })
})

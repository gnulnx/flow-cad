import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import AppShell from './AppShell'
import type { InventorySnapshot, SaveMeasurementSnapshotInput, WorkbenchPart } from './contracts'
import { createTestWorkbenchClient } from './testClient'

function part(key: string, overrides: Partial<WorkbenchPart> = {}): WorkbenchPart {
  return {
    uuid: `${key}-uuid`,
    key,
    aliases: [],
    role: 'printable',
    status: 'active',
    artifactState: 'indexed',
    geometryAuthority: 'step',
    qualityLabel: 'Exact',
    occurrenceCount: 1,
    occurrenceIds: [`${key}-occurrence`],
    occurrences: [{
      assemblyId: 'active',
      id: `${key}-occurrence`,
      translationMm: [0, 0, 0],
      rotationDeg: [0, 0, 0],
    }],
    authorityHash: `${key}-step-sha`,
    displayArtifact: null,
    bounds: null,
    warnings: [],
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

describe('replacement AppShell', () => {
  it('renders the shell, viewport state, and permanent chat before inventory resolves', async () => {
    const inventory = deferred<InventorySnapshot>()
    render(<AppShell client={createTestWorkbenchClient({ inventory: inventory.promise })} />)

    expect(screen.getByLabelText('Flow CAD Workbench')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Parts' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Assembly review' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Design chat' })).toBeInTheDocument()
    expect(screen.getByText('Loading metadata…')).toBeInTheDocument()
    expect(screen.getByText('Select a part to begin')).toBeInTheDocument()

    inventory.resolve({ revision: 7, activeAssemblyId: 'active', parts: [part('unitree_l2_arch_guard')] })
    expect(await screen.findByRole('option', { name: /unitree_l2_arch_guard/ })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'unitree_l2_arch_guard' })).toBeInTheDocument()
  })

  it('searches keys and aliases while keeping authority and failure states explicit', async () => {
    const user = userEvent.setup()
    render(<AppShell client={createTestWorkbenchClient({
      inventory: {
        revision: 9,
        activeAssemblyId: 'active',
        parts: [
          part('arch_guard', { aliases: ['unitree_l2_arch_guard'] }),
          part('missing_bracket', {
            artifactState: 'missing',
            geometryAuthority: 'missing',
            qualityLabel: 'Missing',
            status: 'preserved-only',
          }),
        ],
      },
    })} />)

    const search = await screen.findByPlaceholderText('Search parts or aliases')
    await user.type(search, 'unitree')
    const inventory = within(screen.getByRole('listbox', { name: 'Project parts' }))
    expect(inventory.getByText('arch_guard')).toBeInTheDocument()
    expect(inventory.queryByText('missing_bracket')).not.toBeInTheDocument()

    await user.clear(search)
    expect(inventory.getByText('missing_bracket')).toBeInTheDocument()
    expect(inventory.getByText('Missing')).toBeInTheDocument()
  })

  it('restores and durably saves thread-bound measurement label state', async () => {
    const user = userEvent.setup()
    const saveMeasurementSnapshot = vi.fn(async (_input: SaveMeasurementSnapshotInput) => undefined)
    const partUuid = '11111111-1111-4111-8111-111111111111'
    const revision = 'a'.repeat(64)
    render(<AppShell client={createTestWorkbenchClient({
      inventory: { revision: 9, activeAssemblyId: 'active', parts: [part('arch_guard', { uuid: partUuid, authorityHash: revision })] },
      latestMeasurementSnapshot: {
        threadId: 'default',
        partUuid,
        artifactRevision: revision,
        measurements: [{
          measurementId: 'measurement-1',
          kind: 'distance',
          title: 'Exact vertex to Exact vertex',
          quality: 'exact',
          startMm: [0, 0, 0],
          endMm: [3, 4, 0],
          totalMm: 5,
          deltaMm: [3, 4, 0],
          featureIds: ['vertex-1', 'vertex-2'],
          hidden: false,
          pinned: true,
          labelOffsetPx: [0, 0],
        }],
      },
      saveMeasurementSnapshot,
    })} />)

    expect(await screen.findByText('5.00 mm')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Unpin' }))
    await waitFor(() => expect(saveMeasurementSnapshot).toHaveBeenCalledOnce())
    expect(saveMeasurementSnapshot.mock.calls[0][0]).toMatchObject({
      threadId: 'default',
      partUuid,
      artifactRevision: revision,
      measurements: [{ measurementId: 'measurement-1', pinned: false }],
    })
  })
})

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import AppShell from './AppShell'
import type { InventorySnapshot, WorkbenchPart } from './contracts'
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

    inventory.resolve({ revision: 7, parts: [part('unitree_l2_arch_guard')] })
    expect(await screen.findByRole('option', { name: /unitree_l2_arch_guard/ })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'unitree_l2_arch_guard' })).toBeInTheDocument()
  })

  it('searches keys and aliases while keeping authority and failure states explicit', async () => {
    const user = userEvent.setup()
    render(<AppShell client={createTestWorkbenchClient({
      inventory: {
        revision: 9,
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
})

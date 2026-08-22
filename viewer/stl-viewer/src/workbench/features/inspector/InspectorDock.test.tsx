import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { createTestWorkbenchClient } from '../../testClient'
import { InspectorDock } from './InspectorDock'

const ACTIVE_PART: WorkbenchPart = {
  uuid: 'guard-uuid',
  key: 'arch_guard',
  aliases: [],
  role: 'printable',
  status: 'active',
  artifactState: 'indexed',
  geometryAuthority: 'step',
  qualityLabel: 'Exact',
  occurrenceCount: 1,
  occurrenceIds: ['guard-main'],
  occurrences: [],
  authorityHash: 'step-sha',
  displayArtifact: null,
  bounds: null,
  warnings: [],
}

describe('InspectorDock scoped build', () => {
  it('submits only the selected active part and exposes the durable job', async () => {
    const user = userEvent.setup()
    const buildPart = vi.fn(async (_partIdentity: string, _requestId: string) => ({
      id: 'job-1', label: 'Build arch_guard', state: 'queued' as const, phase: 'queued', progress: 0,
      cancellable: true, elapsedMs: 0, lastUpdate: 'now',
    }))
    const onBuildSubmitted = vi.fn()
    render(<InspectorDock client={createTestWorkbenchClient({ buildPart })} part={ACTIVE_PART} onBuildSubmitted={onBuildSubmitted} />)

    await user.click(screen.getByRole('button', { name: 'Build selected part' }))

    expect(buildPart).toHaveBeenCalledOnce()
    expect(buildPart.mock.calls[0][0]).toBe('guard-uuid')
    expect(onBuildSubmitted).toHaveBeenCalledWith('job-1')
  })

  it('does not expose regeneration for preserved-only inventory', () => {
    render(<InspectorDock client={createTestWorkbenchClient()} part={{ ...ACTIVE_PART, status: 'preserved-only' }} />)
    expect(screen.queryByRole('button', { name: 'Build selected part' })).not.toBeInTheDocument()
  })
})

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
  it('offers existing STEP and STL downloads for inspection views as well as printable parts', () => {
    render(<InspectorDock client={createTestWorkbenchClient()} part={{ ...ACTIVE_PART,
      category: 'view', role: 'inspection', status: 'inspection',
      downloads: [
        { kind: 'step', url: '/models/study-step?download=true', filename: 'study.step' },
        { kind: 'stl', url: '/models/study-stl?download=true', filename: 'study.stl' },
      ],
    }} />)
    expect(screen.getByRole('link', { name: 'Download STEP' })).toHaveAttribute('download', 'study.step')
    expect(screen.getByRole('link', { name: 'Download STL' })).toHaveAttribute('download', 'study.stl')
    expect(screen.queryByRole('button', { name: 'Build selected part' })).not.toBeInTheDocument()
  })
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

  it('copies the exact part key and links only this part’s built files', async () => {
    const user = userEvent.setup()
    const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    render(<InspectorDock client={createTestWorkbenchClient()} part={{ ...ACTIVE_PART,
      downloads: [{ kind: 'step', url: '/api/models/exact?download=true', filename: 'arch_guard.step' },
        { kind: 'stl', url: '/api/models/mesh?download=true', filename: 'arch_guard.stl' }],
    }} />)
    await user.click(screen.getByRole('button', { name: 'Copy part name' }))
    expect(copy).toHaveBeenCalledWith('arch_guard')
    expect(screen.getByRole('link', { name: 'Download STEP' })).toHaveAttribute('href', '/api/models/exact?download=true')
    expect(screen.getByRole('link', { name: 'Download STL' })).toHaveAttribute('download', 'arch_guard.stl')
  })
})

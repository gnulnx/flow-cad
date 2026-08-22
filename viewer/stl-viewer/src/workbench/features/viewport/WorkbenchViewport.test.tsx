import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { createTestWorkbenchClient } from '../../testClient'
import { WorkbenchViewport } from './WorkbenchViewport'

afterEach(() => vi.unstubAllGlobals())

function assemblyPart(index: number): WorkbenchPart {
  return {
    uuid: `part-${index}`,
    key: `part_${index}`,
    aliases: [],
    role: 'printable',
    status: 'active',
    artifactState: 'indexed',
    geometryAuthority: 'step',
    qualityLabel: 'Exact',
    occurrenceCount: 1,
    occurrenceIds: [`occurrence-${index}`],
    occurrences: [{
      assemblyId: 'active',
      id: `occurrence-${index}`,
      translationMm: [index * 10, 0, 0],
      rotationDeg: [0, 0, 0],
    }],
    authorityHash: `step-${index}`,
    displayArtifact: {
      contentHash: `stl-${index}`,
      format: 'stl',
      url: `/api/models/stl-${index}`,
      revision: 7,
    },
    bounds: null,
    warnings: [],
  }
}

describe('WorkbenchViewport measurement integration', () => {
  it('mounts annotation beside measurement and restores the normal left-drag camera contract on exit', async () => {
    const user = userEvent.setup()
    render(<WorkbenchViewport client={createTestWorkbenchClient()} part={null} backendRevision={7} />)

    const button = screen.getByRole('button', { name: 'Measure exact geometry' })
    expect(screen.getByRole('button', { name: 'Annotate' })).toHaveAttribute('aria-pressed', 'false')
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText(/Left rotate/)).toBeInTheDocument()

    await user.keyboard('m')
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/Left select/)).toBeInTheDocument()
    expect(screen.getByText('Select a visible STEP-backed part')).toBeInTheDocument()

    await user.click(button)
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText(/Left rotate/)).toBeInTheDocument()
  })

  it('shows progressive assembly feedback and holds network fan-out to three models', async () => {
    const responders: Array<(response: Response) => void> = []
    const fetchMock = vi.fn((_input: RequestInfo | URL) => new Promise<Response>((resolve) => responders.push(resolve)))
    vi.stubGlobal('fetch', fetchMock)
    const parts = Array.from({ length: 5 }, (_, index) => assemblyPart(index))
    const view = render(
      <WorkbenchViewport
        client={createTestWorkbenchClient()}
        parts={parts}
        part={parts[4]}
        activeAssemblyId="active"
        backendRevision={7}
      />,
    )

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/models/stl-4')
    expect(screen.getByText(/0 of 5 visible/)).toBeInTheDocument()

    responders[0](new Response(new TextEncoder().encode('solid empty\nendsolid empty')))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))
    expect(screen.getByLabelText('Assembly loading progress')).toHaveAttribute('max', '5')
    view.unmount()
  })
})

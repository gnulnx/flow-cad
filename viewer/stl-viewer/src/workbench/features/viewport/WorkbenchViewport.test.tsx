import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { createTestWorkbenchClient } from '../../testClient'
import { WorkbenchViewport } from './WorkbenchViewport'

describe('WorkbenchViewport measurement integration', () => {
  it('exposes one Measure control and restores the normal left-drag camera contract on exit', async () => {
    const user = userEvent.setup()
    render(<WorkbenchViewport client={createTestWorkbenchClient()} part={null} backendRevision={7} />)

    const button = screen.getByRole('button', { name: 'Measure exact geometry' })
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
})

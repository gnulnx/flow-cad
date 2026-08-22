import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { ThreadMessage } from '../../contracts'
import { createTestWorkbenchClient } from '../../testClient'
import { ChatDock } from './ChatDock'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

describe('ChatDock feedback contract', () => {
  it('creates an optimistic assistant row immediately and attaches exact selection context', async () => {
    const user = userEvent.setup()
    const response = deferred<ThreadMessage>()
    let selectedPartUuid: string | null = null
    const client = createTestWorkbenchClient({
      sendTurn: async (input) => {
        selectedPartUuid = input.context.selectedPartUuid
        return response.promise
      },
    })
    render(
      <ChatDock
        client={client}
        available
        context={{
          projectRevision: 12,
          selectedPartUuid: 'guard-uuid',
          selectedPartKey: 'unitree_l2_arch_guard',
          visibleOccurrenceIds: ['guard-occurrence'],
          artifactHashes: { 'guard-uuid': 'display-sha' },
        }}
      />,
    )

    const composer = await screen.findByPlaceholderText('Ask about this part or view…')
    await user.type(composer, 'Check the two mounting centers')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    expect(screen.getByText('Starting…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(selectedPartUuid).toBe('guard-uuid')

    response.resolve({ id: 'answer', role: 'assistant', content: 'Both centers are exact STEP features.', state: 'complete' })
    expect(await screen.findByText('Both centers are exact STEP features.')).toBeInTheDocument()
  })

  it('keeps the dock present and viewing-safe when no provider is configured', async () => {
    render(
      <ChatDock
        client={createTestWorkbenchClient()}
        available={false}
        context={{ projectRevision: 1, selectedPartUuid: null, selectedPartKey: null, visibleOccurrenceIds: [], artifactHashes: {} }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Design chat' })).toBeInTheDocument()
    expect(screen.getByText('No agent provider configured. Viewing remains fully available.')).toBeInTheDocument()
    expect(await screen.findByPlaceholderText('Ask about this part or view…')).toBeDisabled()
  })
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ThreadMessage } from '../../contracts'
import { createTestWorkbenchClient } from '../../testClient'
import { ChatDock } from './ChatDock'

const EMPTY_CONTEXT = {
  projectRevision: 1,
  selectedPartUuid: null,
  selectedPartKey: null,
  visibleOccurrenceIds: [] as string[],
  artifactHashes: {} as Record<string, string>,
  camera: {},
  measurements: [] as Record<string, unknown>[],
  annotations: [] as Record<string, unknown>[],
  viewportAttachment: null,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

describe('ChatDock feedback contract', () => {
  it('publishes the current durable thread for viewport context features', async () => {
    const onThreadChange = vi.fn()
    render(
      <ChatDock
        client={createTestWorkbenchClient()}
        available
        context={EMPTY_CONTEXT}
        onThreadChange={onThreadChange}
      />,
    )

    expect(await screen.findByText('Design review')).toBeInTheDocument()
    expect(onThreadChange).toHaveBeenLastCalledWith('default')
  })

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
          camera: { position: [1, 2, 3] },
          measurements: [{ totalMm: 42 }],
          annotations: [{ kind: 'arrow' }],
          viewportAttachment: { captureId: 'capture-1' },
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
        context={EMPTY_CONTEXT}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Design chat' })).toBeInTheDocument()
    expect(screen.getByText('No agent provider configured. Viewing remains fully available.')).toBeInTheDocument()
    expect(await screen.findByPlaceholderText('Ask about this part or view…')).toBeDisabled()
  })

  it('streams bounded activity, content, evidence, and a terminal result into one row', async () => {
    const user = userEvent.setup()
    const client = createTestWorkbenchClient({
      sendTurn: async () => ({
        id: 'assistant-1',
        turnId: 'turn-1',
        afterSequence: 2,
        role: 'assistant',
        content: 'Agent is working…',
        state: 'streaming',
      }),
      streamTurn: async (_threadId, turnId, _afterSequence, onEvent) => {
        onEvent({ sequence: 3, eventId: 'progress-1', turnId, eventType: 'assistant_progress', payload: { content: 'Inspecting exact STEP facts.' } })
        onEvent({ sequence: 4, eventId: 'delta-1', turnId, eventType: 'assistant_delta', payload: { content: 'The guard is aligned.' } })
        onEvent({ sequence: 5, eventId: 'evidence-1', turnId, eventType: 'assistant_evidence', payload: { artifact_hash: 'a'.repeat(64) } })
        onEvent({ sequence: 6, eventId: 'done-1', turnId, eventType: 'assistant_completed', payload: {} })
      },
    })
    render(<ChatDock client={client} available context={EMPTY_CONTEXT} />)

    await user.type(await screen.findByPlaceholderText('Ask about this part or view…'), 'Inspect')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText('The guard is aligned.')).toBeInTheDocument()
    expect(screen.getByText('Inspecting exact STEP facts.')).toBeInTheDocument()
    expect(screen.getByText('1 evidence record')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
  })
})

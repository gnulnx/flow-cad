import { useEffect, useRef, useState, type FormEvent } from 'react'
import { applyChatTurnEvent } from '../../client'
import type { ChatContext, DefaultThread, ThreadMessage, WorkbenchClient } from '../../contracts'

interface ChatDockProps {
  client: WorkbenchClient
  context: ChatContext
  available: boolean
  onThreadChange?(threadId: string | null): void
}

function nextRequestId() {
  return globalThis.crypto?.randomUUID?.() ?? `turn-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function ChatDock({ client, context, available, onThreadChange }: ChatDockProps) {
  const [thread, setThread] = useState<DefaultThread | null>(null)
  const [messages, setMessages] = useState<ThreadMessage[]>([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const activeRequestRef = useRef<AbortController | null>(null)
  const activeTurnRef = useRef<{ threadId: string, turnId: string } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    onThreadChange?.(null)
    client.getDefaultThread(controller.signal).then((nextThread) => {
      setThread(nextThread)
      setMessages(nextThread.messages)
      setError(null)
      onThreadChange?.(nextThread.thread.id)
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      setError(reason instanceof Error ? reason.message : 'Chat history unavailable')
      onThreadChange?.(null)
    })
    return () => controller.abort()
  }, [client, onThreadChange])

  const running = messages.some((message) => message.state === 'streaming')

  const cancel = async () => {
    activeRequestRef.current?.abort()
    const activeTurn = activeTurnRef.current
    try {
      if (activeTurn) await client.cancelTurn(activeTurn.threadId, activeTurn.turnId)
      setMessages((current) => current.map((message) => message.state === 'streaming'
        ? { ...message, content: 'Cancelled.', state: 'failed' }
        : message))
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : 'Cancellation failed'
      setMessages((current) => current.map((message) => message.state === 'streaming'
        ? { ...message, content: `Cancellation failed: ${detail}`, state: 'failed' }
        : message))
    } finally {
      activeTurnRef.current = null
    }
  }

  const send = async (event: FormEvent) => {
    event.preventDefault()
    const content = draft.trim()
    if (!thread || !content || running || !available) return
    const requestId = nextRequestId()
    const userMessage: ThreadMessage = { id: `${requestId}-user`, role: 'user', content, state: 'complete' }
    const assistantMessage: ThreadMessage = { id: `${requestId}-assistant`, role: 'assistant', content: 'Starting…', state: 'streaming' }
    setDraft('')
    setMessages((current) => [...current, userMessage, assistantMessage])
    const controller = new AbortController()
    activeRequestRef.current = controller
    try {
      const result = await client.sendTurn({ requestId, threadId: thread.thread.id, content, context }, controller.signal)
      setMessages((current) => current.map((message) => message.id === assistantMessage.id ? result : message))
      if (result.state === 'streaming' && result.turnId) {
        activeTurnRef.current = { threadId: thread.thread.id, turnId: result.turnId }
        await client.streamTurn(
          thread.thread.id,
          result.turnId,
          result.afterSequence ?? 0,
          (turnEvent) => setMessages((current) => current.map((message) => (
            message.turnId === result.turnId ? applyChatTurnEvent(message, turnEvent) : message
          ))),
          controller.signal,
        )
        activeTurnRef.current = null
      }
    } catch (reason) {
      const detail = controller.signal.aborted ? 'Cancelled.' : reason instanceof Error ? reason.message : 'Request failed'
      setMessages((current) => current.map((message) => message.id === assistantMessage.id
        ? { ...message, content: detail, state: 'failed' }
        : message))
    } finally {
      activeRequestRef.current = null
    }
  }

  return (
    <aside className="chat-dock" aria-labelledby="chat-title">
      <div className="dock-heading chat-heading">
        <div>
          <span className="eyebrow">Persistent context</span>
          <h2 id="chat-title">Design chat</h2>
        </div>
        <span className={`chat-state ${running ? 'chat-state--running' : ''}`}>{running ? 'Working' : thread ? 'Ready' : 'Opening'}</span>
      </div>
      <div className="thread-title">
        <strong>{thread?.thread.title ?? 'Default design thread'}</strong>
        <span>{thread ? 'Saved with this project' : error ? 'History unavailable' : 'Loading history…'}</span>
      </div>
      <div className="context-packet" aria-label="Attached CAD context">
        <span>Context</span>
        <button type="button" title="Project revision">rev {context.projectRevision ?? '—'}</button>
        <button type="button" title="Selected part">{context.selectedPartKey ?? 'no part'}</button>
        <button type="button" title="Visible occurrences">{context.visibleOccurrenceIds.length} visible</button>
        <details className="context-inspector">
          <summary>Inspect</summary>
          <pre>{JSON.stringify({
            selectedPartUuid: context.selectedPartUuid,
            visibleOccurrenceIds: context.visibleOccurrenceIds,
            artifactHashes: context.artifactHashes,
            camera: context.camera,
            measurements: context.measurements,
            annotations: context.annotations,
            viewportAttachment: context.viewportAttachment,
            viewerRevision: context.projectRevision,
          }, null, 2)}</pre>
        </details>
      </div>
      <div className="chat-transcript" aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <span aria-hidden="true">⌁</span>
            <strong>CAD context stays attached</strong>
            <p>Ask about the selected part, current view, measurements, or a focused rebuild.</p>
          </div>
        ) : messages.map((message) => (
          <article className={`chat-message chat-message--${message.role}`} data-state={message.state} key={message.id}>
            <span>{message.role === 'assistant' ? 'Flow agent' : 'You'}</span>
            <p>{message.content}</p>
            {message.activity?.length ? (
              <ul className="chat-activity" aria-label="Agent activity">
                {message.activity.map((activity, index) => <li key={`${message.id}-activity-${index}`}>{activity}</li>)}
              </ul>
            ) : null}
            {message.evidence?.length ? <span className="chat-evidence">{message.evidence.length} evidence record{message.evidence.length === 1 ? '' : 's'}</span> : null}
          </article>
        ))}
      </div>
      {error ? <div className="chat-notice">Chat history unavailable: {error}</div> : null}
      {!available ? <div className="chat-notice">No agent provider configured. Viewing remains fully available.</div> : null}
      <form className="chat-composer" onSubmit={send}>
        <label>
          <span className="sr-only">Message design agent</span>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask about this part or view…"
            rows={3}
            disabled={!thread || !available}
          />
        </label>
        <div>
          <span>{context.selectedPartKey ? `Attached: ${context.selectedPartKey}` : 'Select a part for exact context'}</span>
          {running ? (
            <button type="button" className="button-danger" onClick={() => void cancel()}>Cancel</button>
          ) : (
            <button type="submit" disabled={!thread || !available || !draft.trim()}>Send</button>
          )}
        </div>
      </form>
    </aside>
  )
}

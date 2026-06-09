import { FormEvent, useMemo, useState } from 'react'
import CommandPane from './CommandPane'
import SourcePanel from './SourcePanel'
import type {
  CreateDesignThreadPayload,
  DesignThreadEvent,
  DesignThreadRecord,
  DesignThreadSummary,
  SourceContext,
  ThreadContextSnapshot,
  DesignThreadChatPayload,
  DesignThreadChatResponse,
} from '../types'
import type { PreviewContext, ProposedPreviewOperation, DraftAcceptanceArtifacts, DraftPreviewModelPayload } from '../types'

interface DesignThreadDockProps {
  activeTab: 'source' | 'chat'
  onTabChange: (tab: 'source' | 'chat') => void
  sourceContext: SourceContext | null
  activePartId: string | null
  leftDockCollapsed: boolean
  sourceWidth: number
  onToggleLeftDock: () => void
  leftDockResizing: boolean
  threads: DesignThreadSummary[]
  activeThreadId: string | null
  activeThread: DesignThreadRecord | null
  threadBusy: boolean
  isThreadMuted: boolean
  selectedPartIds: string[]
  visiblePartIds: string[]
  activeProjectRevision: number | null
  activeAssemblyId: string | null
  previewModel: DraftPreviewModelPayload | null
  acceptedArtifacts: DraftAcceptanceArtifacts | null
  proposalWarnings: string[]
  proposedOperations: ProposedPreviewOperation[]
  hasTransaction: boolean
  commandBusy: {
    propose: boolean
    apply: boolean
    preview: boolean
    accept: boolean
    discard: boolean
  }
  previewContext: PreviewContext | null
  commandText: string
  onCommandChange: (value: string) => void
  onPropose: () => void
  onApply: () => void
  onPreview: () => void
  onAccept: () => void
  onDiscard: () => void
  onResetCommand: () => void
  onCreateThread: (payload: CreateDesignThreadPayload) => Promise<void>
  onActivateThread: (threadId: string) => Promise<unknown>
  onPatchThread: (threadId: string, patch: Record<string, unknown>) => Promise<unknown>
  onSendChatMessage: (threadId: string, payload: DesignThreadChatPayload) => Promise<DesignThreadChatResponse>
  onBuildViewerContext: () => Record<string, unknown>
  onCreateContextSnapshot: (threadId: string, payload: Record<string, unknown>) => Promise<ThreadContextSnapshot | null>
}

function eventContentText(event: DesignThreadEvent) {
  if (typeof event.content === 'string') return event.content
  if (event.content && typeof event.content === 'object') {
    if (typeof (event.content as Record<string, unknown>).summary === 'string') {
      return String((event.content as Record<string, unknown>).summary)
    }
    try {
      return JSON.stringify(event.content)
    } catch {
      return String(event.content)
    }
  }
  return ''
}

export default function DesignThreadDock({
  activeTab,
  onTabChange,
  sourceContext,
  activePartId,
  leftDockCollapsed,
  sourceWidth,
  onToggleLeftDock,
  leftDockResizing,
  threads,
  activeThreadId,
  activeThread,
  threadBusy,
  isThreadMuted,
  selectedPartIds,
  visiblePartIds,
  activeProjectRevision,
  activeAssemblyId,
  previewModel,
  acceptedArtifacts,
  proposalWarnings,
  proposedOperations,
  hasTransaction,
  commandBusy,
  previewContext,
  commandText,
  onCommandChange,
  onPropose,
  onApply,
  onPreview,
  onAccept,
  onDiscard,
  onResetCommand,
  onCreateThread,
  onActivateThread,
  onPatchThread,
  onSendChatMessage,
  onBuildViewerContext,
  onCreateContextSnapshot,
}: DesignThreadDockProps) {
  const [composerText, setComposerText] = useState('')
  const [createTitle, setCreateTitle] = useState('')
  const [pendingSnapshotId, setPendingSnapshotId] = useState<string | null>(null)
  const [snapshotError, setSnapshotError] = useState<string | null>(null)
  const [snapshotBusy, setSnapshotBusy] = useState(false)
  const [chatBusy, setChatBusy] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const [threadsOpen, setThreadsOpen] = useState(false)
  const [renamingThreadId, setRenamingThreadId] = useState<string | null>(null)
  const [renameTitle, setRenameTitle] = useState('')

  const selectedThread = activeThreadId ? threads.find((thread) => thread.thread_id === activeThreadId) : null
  const events = activeThread?.messages ?? []
  const contextChipItems = useMemo(
    () => {
      const selected = selectedPartIds.length ? `${selectedPartIds.length} selected` : 'no selection'
      const visible = visiblePartIds.length ? `${visiblePartIds.length} visible` : 'nothing visible'
      const revision = activeProjectRevision !== null ? `rev ${activeProjectRevision}` : 'no revision'
      const assembly = activeAssemblyId ?? 'no assembly'
      return {
        selected,
        visible,
        revision,
        assembly,
      }
    },
    [activeAssemblyId, activeProjectRevision, selectedPartIds.length, visiblePartIds.length],
  )

  const commandBusyState = useMemo(
    () => !activeThreadId || isThreadMuted || threadBusy || chatBusy,
    [activeThreadId, chatBusy, isThreadMuted, threadBusy],
  )

  const createThread = async () => {
    await onCreateThread({
      title: createTitle.trim().length ? createTitle.trim() : `Thread ${new Date().toISOString()}`,
    })
    setCreateTitle('')
    setThreadsOpen(false)
  }

  const saveThreadTitle = async (threadId: string) => {
    if (!renameTitle.trim()) {
      setRenamingThreadId(null)
      return
    }
    await onPatchThread(threadId, { title: renameTitle.trim() })
    setRenamingThreadId(null)
    setRenameTitle('')
  }

  const createSnapshot = async () => {
    if (!activeThreadId) return
    setSnapshotBusy(true)
    setSnapshotError(null)
    try {
      const payload = onBuildViewerContext()
      const snapshot = await onCreateContextSnapshot(activeThreadId, payload)
      setPendingSnapshotId(snapshot?.snapshot_id ?? null)
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Failed to capture context')
    } finally {
      setSnapshotBusy(false)
    }
  }

  const clearComposer = () => {
    setComposerText('')
    setPendingSnapshotId(null)
    setSnapshotError(null)
  }

  const sendMessage = async (event: FormEvent) => {
    event.preventDefault()
    if (!activeThreadId) return
    if (!composerText.trim()) return
    setChatBusy(true)
    setChatError(null)
    try {
      await onSendChatMessage(activeThreadId, {
        message: composerText.trim(),
        context_snapshot: onBuildViewerContext(),
      })
      clearComposer()
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'Chat request failed')
    } finally {
      setChatBusy(false)
    }
  }

  return (
    <section
      className={`sidebar-dock left-dock ${leftDockCollapsed ? 'collapsed' : ''} ${leftDockResizing ? 'resizing' : ''}`}
      style={{ width: leftDockCollapsed ? undefined : sourceWidth }}
      aria-label="Design thread dock"
    >
      <div className="sidebar-icon-strip" onClick={onToggleLeftDock} title="Expand design workspace">
        <button type="button" className="icon-strip-btn" aria-label="Expand design workspace">C</button>
        <div style={{
          writingMode: 'vertical-lr',
          textTransform: 'uppercase',
          fontSize: '11px',
          fontWeight: 700,
          letterSpacing: '0.1em',
          color: 'var(--text-secondary)',
        }}>Chat</div>
      </div>
      <div className="sidebar-content">
        <div className="dock-tabset" role="tablist" aria-label="Design view tabs">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'source'}
            className={`dock-tab ${activeTab === 'source' ? 'active' : ''}`}
            onClick={() => onTabChange('source')}
          >
            Source
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'chat'}
            className={`dock-tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => onTabChange('chat')}
          >
            Chat
          </button>
        </div>
        {activeTab === 'source' ? (
          <div className="dock-source">
            <SourcePanel
              context={sourceContext}
              activeId={activePartId}
              collapsed={leftDockCollapsed}
              onToggle={onToggleLeftDock}
              standalone={false}
            />
          </div>
        ) : (
          <div className="design-chat-workspace">
            <header className="chat-header">
              <div className="chat-title-block">
                <h2>{selectedThread?.title ?? 'Design Chat'}</h2>
                <p>{selectedThread ? `${events.length} messages` : 'Create or select a thread'}</p>
              </div>
              <div className="chat-header-actions">
                <button
                  type="button"
                  className="btn-tool"
                  onClick={() => setThreadsOpen((value) => !value)}
                  aria-expanded={threadsOpen}
                  aria-controls="thread-drawer"
                >
                  Threads
                </button>
                <button
                  type="button"
                  className="btn-tool"
                  onClick={() => onPatchThread(activeThreadId ?? '', { archived: true })}
                  disabled={!activeThreadId || isThreadMuted}
                  aria-label="Archive thread"
                >
                  Archive
                </button>
              </div>
            </header>

            {threadsOpen ? (
              <section id="thread-drawer" className="thread-drawer" aria-label="Thread manager">
                <form
                  className="thread-form"
                  onSubmit={(event) => {
                    event.preventDefault()
                    if (!isThreadMuted) void createThread()
                  }}
                >
                  <input
                    value={createTitle}
                    onChange={(event) => setCreateTitle(event.target.value)}
                    placeholder="New thread title"
                    aria-label="New thread title"
                  />
                  <button
                    type="submit"
                    className="btn-tool"
                    disabled={isThreadMuted}
                    aria-label="Create new design thread"
                  >
                    Create
                  </button>
                </form>
                <ul className="thread-list" role="list">
                  {threads.map((thread) => (
                    <li
                      key={thread.thread_id}
                      className={`thread-list-item ${thread.thread_id === activeThreadId ? 'active' : ''}`}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          void onActivateThread(thread.thread_id)
                          setThreadsOpen(false)
                        }}
                        className="thread-title"
                        disabled={isThreadMuted}
                        aria-label={`Open thread ${thread.title}`}
                      >
                        {thread.title || 'Untitled'}
                      </button>
                      {thread.thread_id === activeThreadId && renamingThreadId ? (
                        <form
                          className="thread-rename-form"
                          onSubmit={(event) => {
                            event.preventDefault()
                            void saveThreadTitle(thread.thread_id)
                          }}
                        >
                          <input
                            value={renameTitle}
                            onChange={(event) => setRenameTitle(event.target.value)}
                            aria-label="Rename thread"
                          />
                          <button type="submit" className="btn-tool" aria-label="Save thread title">
                            Save
                          </button>
                        </form>
                      ) : null}
                      {thread.thread_id === activeThreadId && !renamingThreadId ? (
                        <button
                          type="button"
                          className="thread-inline-action"
                          onClick={() => {
                            setRenamingThreadId(thread.thread_id)
                            setRenameTitle(thread.title)
                          }}
                          aria-label="Rename thread"
                        >
                          Rename
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <div className="chat-context-strip" aria-label="Context chips">
              <span>{contextChipItems.selected}</span>
              <span>{contextChipItems.visible}</span>
              <span>{contextChipItems.revision}</span>
              <span>{contextChipItems.assembly}</span>
            </div>

            <div className="chat-context-actions">
              <button
                type="button"
                className="btn-tool"
                onClick={() => void createSnapshot()}
                disabled={snapshotBusy || !activeThreadId || isThreadMuted}
              >
                {snapshotBusy ? 'Capturing...' : 'Attach view'}
              </button>
              {pendingSnapshotId ? (
                <span className="context-pill" role="status">
                  View attached:
                  {' '}
                  <span>{pendingSnapshotId}</span>
                </span>
              ) : null}
              {snapshotError ? <span className="thread-error">{snapshotError}</span> : null}
              {chatError ? <span className="thread-error">{chatError}</span> : null}
            </div>

            <div className="chat-message-list" aria-label="Message history">
              {events.length ? (
                events.map((event) => (
                  <article key={event.message_id} className={`chat-message chat-message-${event.role ?? event.type}`}>
                    <div className="chat-message-avatar">{event.role === 'assistant' ? 'AI' : 'You'}</div>
                    <div className="chat-message-bubble">
                      <div className="chat-message-meta">
                        <span>{event.type}</span>
                        <span>{event.created_at ?? ''}</span>
                      </div>
                      <p>{eventContentText(event)}</p>
                      {event.metadata?.context_snapshot_id ? (
                        <div className="context-pill">view {String(event.metadata.context_snapshot_id)}</div>
                      ) : null}
                      {event.attachments?.length ? (
                        <ul className="thread-message-attachments">
                          {event.attachments.map((attachment) => (
                            <li key={attachment}>{attachment}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  </article>
                ))
              ) : (
                <div className="chat-empty">Start with a design note. The current viewport is sent with each message.</div>
              )}
            </div>

            <form className="chat-composer" onSubmit={sendMessage}>
              <textarea
                id="thread-composer-textarea"
                value={composerText}
                onChange={(event) => setComposerText(event.target.value)}
                disabled={commandBusyState}
                rows={3}
                aria-label="Thread message composer"
                placeholder="Ask for a CAD change, inspection, or review..."
              />
              <div className="chat-composer-actions">
                <span>{activeThreadId ? 'View context attached on send' : 'Select or create a thread'}</span>
                <button
                  type="submit"
                  className="btn-tool chat-send"
                  disabled={!activeThreadId || !composerText.trim() || commandBusyState}
                >
                  {chatBusy ? 'Sending...' : 'Send'}
                </button>
              </div>
            </form>

            <details className="advanced-thread-tools">
              <summary>Advanced draft tools</summary>
              <CommandPane
                selectedPartId={activePartId}
                context={previewContext}
                commandText={commandText}
                proposalWarnings={proposalWarnings}
                proposedOperations={proposedOperations}
                previewModel={previewModel}
                acceptanceArtifacts={acceptedArtifacts}
                busy={commandBusy}
                hasTransaction={hasTransaction}
                onCommandChange={onCommandChange}
                onPropose={onPropose}
                onApply={onApply}
                onPreview={onPreview}
                onAccept={onAccept}
                onDiscard={onDiscard}
                onReset={onResetCommand}
              />
            </details>
          </div>
        )}
      </div>
    </section>
  )
}

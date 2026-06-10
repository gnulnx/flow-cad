import { FormEvent, useMemo, useState } from 'react'
import CommandPane from './CommandPane'
import SourcePanel from './SourcePanel'
import type {
  CreateDesignThreadPayload,
  DesignThreadEvent,
  DesignThreadRecord,
  DesignThreadSummary,
  ThreadVisualEvidenceArtifact,
  VisualEvidenceViewPreset,
  SourceContext,
  DesignThreadChatPayload,
  DesignThreadChatResponse,
  ThreadViewportAnnotation,
  ViewportMarkupTool,
  ViewportAttachmentRecord,
  ViewportScreenshotPayload,
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
  onCreateViewportAttachment: (threadId: string, payload: ViewportScreenshotPayload) => Promise<ViewportAttachmentRecord | null>
  onRequestVisualEvidence?: (threadId: string) => Promise<ThreadVisualEvidenceArtifact | null>
  visualEvidenceView: VisualEvidenceViewPreset
  onVisualEvidenceViewChange: (view: VisualEvidenceViewPreset) => void
  threadVisualEvidence: ThreadVisualEvidenceArtifact[]
  threadVisualEvidenceCount?: number
  onBuildViewerContext: (options?: { includeViewportScreenshot?: boolean }) => Record<string, unknown>
  threadAttachmentIds: string[]
  markupActive: boolean
  markupTool: ViewportMarkupTool
  markupNoteText: string
  markupAnnotations: ThreadViewportAnnotation[]
  onMarkupActiveChange: (active: boolean) => void
  onMarkupToolChange: (tool: ViewportMarkupTool) => void
  onMarkupNoteTextChange: (value: string) => void
  onClearMarkup: () => void
  onUndoMarkup: () => void
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

function eventActor(event: DesignThreadEvent) {
  if (event.role === 'user') return 'You'
  if (event.type === 'draft_event') return 'Draft'
  return 'AI'
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
  onCreateViewportAttachment,
  onRequestVisualEvidence,
  visualEvidenceView,
  onVisualEvidenceViewChange,
  threadVisualEvidence,
  threadVisualEvidenceCount,
  onBuildViewerContext,
  threadAttachmentIds,
  markupActive,
  markupTool,
  markupNoteText,
  markupAnnotations,
  onMarkupActiveChange,
  onMarkupToolChange,
  onMarkupNoteTextChange,
  onClearMarkup,
  onUndoMarkup,
}: DesignThreadDockProps) {
  const [composerText, setComposerText] = useState('')
  const [createTitle, setCreateTitle] = useState('')
  const [snapshotError, setSnapshotError] = useState<string | null>(null)
  const [snapshotBusy, setSnapshotBusy] = useState(false)
  const [visualEvidenceBusy, setVisualEvidenceBusy] = useState(false)
  const [visualEvidenceError, setVisualEvidenceError] = useState<string | null>(null)
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

  const createViewportAttachment = async () => {
    if (!activeThreadId) return
    setSnapshotBusy(true)
    setSnapshotError(null)
    try {
      const payload = onBuildViewerContext({ includeViewportScreenshot: true })
      const screenshotPayload = (payload.viewport_screenshot as { data_url?: unknown } | undefined)
      const payloadForAttachment = {
        kind: 'viewport_screenshot',
        content_type: 'image/png',
        selected_part_ids: payload.selected_part_ids as string[],
        visible_part_ids: payload.visible_part_ids as string[],
        annotations: markupAnnotations,
        backend_revision: payload.active_project_revision,
      } as ViewportScreenshotPayload

      if (typeof screenshotPayload?.data_url === 'string' && screenshotPayload.data_url.trim()) {
        payloadForAttachment.data_url = screenshotPayload.data_url
      } else {
        throw new Error('Viewport screenshot is unavailable')
      }

      if (payload.viewport_size && typeof payload.viewport_size === 'object') {
        const sizeCandidate = payload.viewport_size as { width?: unknown; height?: unknown; client_width?: unknown; client_height?: unknown }
        if (typeof sizeCandidate.width === 'number' && typeof sizeCandidate.height === 'number') {
          payloadForAttachment.viewport = {
            width: sizeCandidate.width,
            height: sizeCandidate.height,
            client_width: typeof sizeCandidate.client_width === 'number' ? sizeCandidate.client_width : undefined,
            client_height: typeof sizeCandidate.client_height === 'number' ? sizeCandidate.client_height : undefined,
          }
        }
      }

      const attachment = await onCreateViewportAttachment(activeThreadId, payloadForAttachment)
      if (attachment) {
        // Parent state updates latestAttachmentId from the returned attachment record.
      }
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Failed to capture context')
    } finally {
      setSnapshotBusy(false)
    }
  }

  const requestVisualEvidence = async () => {
    if (!activeThreadId || !onRequestVisualEvidence) return
    setVisualEvidenceBusy(true)
    setVisualEvidenceError(null)
    try {
      await onRequestVisualEvidence(activeThreadId)
    } catch (error) {
      setVisualEvidenceError(error instanceof Error ? error.message : 'Failed to capture visual evidence')
    } finally {
      setVisualEvidenceBusy(false)
    }
  }

  const clearComposer = () => {
    setComposerText('')
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
                onClick={() => void createViewportAttachment()}
                disabled={snapshotBusy || !activeThreadId || isThreadMuted}
              >
                {snapshotBusy ? 'Capturing...' : 'Attach view'}
              </button>
              {snapshotError ? <span className="thread-error">{snapshotError}</span> : null}
              {chatError ? <span className="thread-error">{chatError}</span> : null}
            </div>

            <div className="chat-context-actions" aria-label="Attachment tray">
              <div className="attachment-tray-title">User attachments</div>
              {threadAttachmentIds.length ? (
                <div className="attachment-tray-list" role="list">
                  {threadAttachmentIds.map((attachmentId) => (
                    <span key={attachmentId} className="context-pill" role="listitem">
                      {attachmentId}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="thread-error">No attachments yet.</span>
              )}
            </div>

            <div className="chat-context-actions" aria-label="Visual evidence tray">
              <div className="chat-context-header">
                <div className="attachment-tray-title">Visual evidence</div>
                {typeof threadVisualEvidenceCount === 'number' ? (
                  <span className="attachment-count">({threadVisualEvidenceCount})</span>
                ) : null}
              </div>
              <button
                type="button"
                className="btn-tool"
                onClick={() => void requestVisualEvidence()}
                disabled={visualEvidenceBusy || !activeThreadId || isThreadMuted || !onRequestVisualEvidence}
              >
                {visualEvidenceBusy ? 'Requesting...' : 'Capture render'}
              </button>
              <select
                className="visual-evidence-view-select"
                aria-label="Visual evidence view"
                value={visualEvidenceView}
                onChange={(event) => onVisualEvidenceViewChange(event.target.value as VisualEvidenceViewPreset)}
                disabled={visualEvidenceBusy || !activeThreadId || isThreadMuted}
              >
                <option value="iso">Iso</option>
                <option value="front">Front</option>
                <option value="back">Back</option>
                <option value="left">Left</option>
                <option value="right">Right</option>
                <option value="top">Top</option>
                <option value="bottom">Bottom</option>
              </select>
              {visualEvidenceError ? <span className="thread-error">{visualEvidenceError}</span> : null}
              {threadVisualEvidence.length ? (
                <ul className="visual-evidence-list" role="list">
                  {threadVisualEvidence.map((artifact) => {
                    const imageHref = artifact.image_url || artifact.image_endpoint || artifact.path
                    return (
                      <li key={artifact.artifact_id} className="visual-evidence-item" role="listitem">
                        <div className="visual-evidence-chips" aria-label={`Evidence ${artifact.artifact_id}`}>
                          <span className="context-pill">source: {artifact.source}</span>
                          <span className="context-pill">view: {artifact.view}</span>
                          {artifact.purpose ? <span className="context-pill">purpose: {artifact.purpose}</span> : null}
                          {artifact.width != null && artifact.height != null ? (
                            <span className="context-pill">size: {artifact.width}x{artifact.height}</span>
                          ) : null}
                        </div>
                        {imageHref ? (
                          <a className="btn-tool visual-evidence-link" href={imageHref} target="_blank" rel="noreferrer">
                            Open image
                          </a>
                        ) : null}
                        <span className="context-pill">id: {artifact.artifact_id}</span>
                      </li>
                    )
                  })}
                </ul>
              ) : (
                <span className="thread-error">No visual evidence yet.</span>
              )}
            </div>

            <div className="chat-context-actions">
              <div className="markup-controls" aria-label="Markup controls">
                <button
                  type="button"
                  className={`btn-tool ${markupActive ? 'active' : ''}`}
                  aria-pressed={markupActive}
                  onClick={() => onMarkupActiveChange(!markupActive)}
                  disabled={!activeThreadId || isThreadMuted}
                >
                  Markup view
                </button>
                {(['pen', 'circle', 'note'] as ViewportMarkupTool[]).map((tool) => (
                  <button
                    key={tool}
                    type="button"
                    className={`btn-tool ${markupTool === tool ? 'active' : ''}`}
                    aria-pressed={markupTool === tool}
                    onClick={() => onMarkupToolChange(tool)}
                    disabled={!markupActive || commandBusyState}
                  >
                    {tool === 'pen' ? 'Pen' : tool === 'circle' ? 'Circle' : 'Text'}
                  </button>
                ))}
                <input
                  type="text"
                  className="markup-note-input"
                  aria-label="Markup text"
                  placeholder="Text label"
                  value={markupNoteText}
                  onChange={(event) => onMarkupNoteTextChange(event.target.value)}
                  disabled={!markupActive || commandBusyState}
                />
                <button
                  type="button"
                  className="btn-tool"
                  onClick={onUndoMarkup}
                  disabled={!markupAnnotations.length || commandBusyState}
                >
                  Undo
                </button>
                <button
                  type="button"
                  className="btn-tool"
                  onClick={onClearMarkup}
                  disabled={!markupAnnotations.length || commandBusyState}
                >
                  Clear
                </button>
                <span className="context-pill">{markupAnnotations.length} markups</span>
              </div>

              {markupAnnotations.length ? (
                <ul className="thread-message-attachments" aria-label="Markup list">
                  {markupAnnotations.map((annotation, index) => (
                    <li key={`${annotation.kind}-${index}`}>
                      {annotation.kind === 'freehand'
                        ? `pen stroke: ${annotation.points.length} points`
                        : annotation.kind === 'note'
                          ? `text: ${annotation.text}`
                          : `circle: (${annotation.x.toFixed(2)}, ${annotation.y.toFixed(2)}), r=${annotation.radius.toFixed(2)}`}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>

            <div className="chat-message-list" aria-label="Message history">
              {events.length ? (
                events.map((event) => (
                  <article key={event.message_id} className={`chat-message chat-message-${event.role ?? event.type}`}>
                    <div className="chat-message-avatar">{eventActor(event)}</div>
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

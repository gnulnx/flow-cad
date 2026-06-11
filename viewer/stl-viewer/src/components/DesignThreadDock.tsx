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
  ViewportAttachmentRecord,
  ViewportScreenshotPayload,
  ThreadVisualEvidenceRequest,
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
  onCommitWorkerJob?: (threadId: string, jobId: string) => Promise<unknown>
  onCreateViewportAttachment: (threadId: string, payload: ViewportScreenshotPayload) => Promise<ViewportAttachmentRecord | null>
  onRequestVisualEvidence?: (threadId: string) => Promise<ThreadVisualEvidenceArtifact | null>
  visualEvidenceView: VisualEvidenceViewPreset
  onVisualEvidenceViewChange: (view: VisualEvidenceViewPreset) => void
  visualEvidenceFollowMode: boolean
  onVisualEvidenceFollowModeChange: (enabled: boolean) => void
  threadVisualEvidence: ThreadVisualEvidenceArtifact[]
  threadVisualEvidenceCount?: number
  threadVisualEvidenceRequests: ThreadVisualEvidenceRequest[]
  threadVisualEvidenceRequestCount?: number
  onBuildViewerContext: (options?: { includeViewportScreenshot?: boolean }) => Record<string, unknown>
  threadAttachmentIds: string[]
}

function eventContentText(event: DesignThreadEvent) {
  if (typeof event.content === 'string') return event.content
  if (event.content && typeof event.content === 'object') {
    const content = event.content as Record<string, unknown>
    if (event.type === 'design_plan') {
      const planType = typeof content.plan_type === 'string' ? content.plan_type : 'plan'
      const steps = Array.isArray(content.steps) ? content.steps : []
      const stepSummaries = steps
        .map((step) => {
          if (!step || typeof step !== 'object' || Array.isArray(step)) return ''
          const record = step as Record<string, unknown>
          return String(record.summary || record.operation_id || record.step_id || '').trim()
        })
        .filter(Boolean)
        .slice(0, 3)
      if (stepSummaries.length) return `${planType}: ${stepSummaries.join(' | ')}`
      return planType
    }
    if (typeof content.summary === 'string') {
      return String(content.summary)
    }
    try {
      return JSON.stringify(content)
    } catch {
      return String(content)
    }
  }
  return ''
}

function eventContentRecord(event: DesignThreadEvent) {
  return event.content && typeof event.content === 'object' && !Array.isArray(event.content)
    ? event.content as Record<string, unknown>
    : null
}

function workerProgressKind(event: DesignThreadEvent) {
  const metadataKind = event.metadata?.worker_progress_kind
  if (typeof metadataKind === 'string' && metadataKind.trim()) return metadataKind.trim()
  const content = eventContentRecord(event)
  const contentKind = content?.kind
  if (typeof contentKind === 'string' && contentKind.startsWith('worker_')) {
    return contentKind.slice('worker_'.length)
  }
  return null
}

function workerProgressStatusClass(status: unknown) {
  const text = String(status || '').toLowerCase()
  if (text === 'completed' || text === 'success' || text === 'succeeded') return 'completed'
  if (text === 'failed' || text === 'error') return 'failed'
  if (text === 'cancelled') return 'cancelled'
  return 'running'
}

function workerProgressStatusLabel(status: unknown) {
  const text = String(status || '').replace(/_/g, ' ').trim()
  return text ? text : 'running'
}

function eventBody(event: DesignThreadEvent) {
  const kind = workerProgressKind(event)
  const content = eventContentRecord(event)
  if (kind && content) {
    const summary = typeof content.summary === 'string' ? content.summary : eventContentText(event)
    if (kind === 'thinking') {
      return (
        <details className="chat-worker-thinking" open>
          <summary>Thinking Process</summary>
          <div className="chat-worker-thinking-content">{summary}</div>
        </details>
      )
    }

    if (kind === 'status') {
      const status = content.status
      return (
        <div className={`chat-worker-card ${workerProgressStatusClass(status)}`}>
          <div className="chat-worker-card-header">
            <span>Worker</span>
            <span>{workerProgressStatusLabel(status)}</span>
          </div>
          <p>{summary}</p>
        </div>
      )
    }

    if (kind === 'command') {
      const status = content.status
      const command = typeof content.command === 'string' ? content.command : summary
      const output = typeof content.output === 'string' ? content.output : ''
      const exitCode = typeof content.exit_code === 'number' ? content.exit_code : null
      return (
        <div className={`chat-worker-card ${workerProgressStatusClass(status)}`}>
          <div className="chat-worker-card-header">
            <span>Command</span>
            <span>{workerProgressStatusLabel(status)}{exitCode !== null ? ` (${exitCode})` : ''}</span>
          </div>
          <code>{command}</code>
          {output ? (
            <details className="chat-worker-output">
              <summary>Output</summary>
              <pre>{output}</pre>
            </details>
          ) : null}
        </div>
      )
    }

    if (kind === 'file_change') {
      const status = content.status
      const paths = Array.isArray(content.paths)
        ? content.paths.filter((path): path is string => typeof path === 'string')
        : []
      return (
        <div className={`chat-worker-card ${workerProgressStatusClass(status)}`}>
          <div className="chat-worker-card-header">
            <span>Source Change</span>
            <span>{workerProgressStatusLabel(status)}</span>
          </div>
          {paths.length ? (
            <ul className="chat-worker-path-list">
              {paths.slice(0, 5).map((path) => <li key={path}>{path}</li>)}
            </ul>
          ) : (
            <p>{summary}</p>
          )}
        </div>
      )
    }

    if (kind === 'error') {
      return <p className="chat-worker-error">{summary}</p>
    }
  }

  return <p>{eventContentText(event)}</p>
}

function eventActor(event: DesignThreadEvent) {
  if (event.role === 'user') return 'You'
  if (event.type === 'draft_event') return 'Draft'
  if (event.type === 'design_plan') return 'Plan'
  const progressKind = workerProgressKind(event)
  if (progressKind && progressKind !== 'thinking') return 'Work'
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
  onCommitWorkerJob,
  onCreateViewportAttachment,
  onRequestVisualEvidence,
  visualEvidenceView,
  onVisualEvidenceViewChange,
  visualEvidenceFollowMode,
  onVisualEvidenceFollowModeChange,
  threadVisualEvidence,
  threadVisualEvidenceCount,
  threadVisualEvidenceRequests,
  threadVisualEvidenceRequestCount,
  onBuildViewerContext,
  threadAttachmentIds,
}: DesignThreadDockProps) {
  const [composerText, setComposerText] = useState('')
  const [createTitle, setCreateTitle] = useState('')
  const [snapshotError, setSnapshotError] = useState<string | null>(null)
  const [snapshotBusy, setSnapshotBusy] = useState(false)
  const [visualEvidenceBusy, setVisualEvidenceBusy] = useState(false)
  const [visualEvidenceError, setVisualEvidenceError] = useState<string | null>(null)
  const [chatBusy, setChatBusy] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const [commitBusy, setCommitBusy] = useState(false)
  const [commitError, setCommitError] = useState<string | null>(null)
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
  const requestStatusCounts = useMemo(() => {
    return threadVisualEvidenceRequests.reduce(
      (counts, request) => {
        const status = String(request.status || 'pending').toLowerCase()
        if (status === 'fulfilled') counts.fulfilled += 1
        else if (status === 'failed') counts.failed += 1
        else if (status === 'in_flight') counts.inFlight += 1
        else counts.pending += 1
        return counts
      },
      { pending: 0, inFlight: 0, fulfilled: 0, failed: 0 },
    )
  }, [threadVisualEvidenceRequests])
  const recentVisualEvidenceRequests = useMemo(
    () => threadVisualEvidenceRequests.slice(-4).reverse(),
    [threadVisualEvidenceRequests],
  )
  const visualEvidenceById = useMemo(() => {
    const byId = new Map<string, ThreadVisualEvidenceArtifact>()
    threadVisualEvidence.forEach((artifact) => {
      if (artifact.artifact_id) byId.set(artifact.artifact_id, artifact)
    })
    return byId
  }, [threadVisualEvidence])
  const commitCandidate = useMemo(() => {
    const jobs = activeThread?.worker_jobs ?? []
    for (let index = jobs.length - 1; index >= 0; index -= 1) {
      const job = jobs[index]
      if (
        job.status === 'succeeded'
        && job.commit_ready
        && Array.isArray(job.changed_paths)
        && job.changed_paths.length > 0
      ) {
        return job
      }
    }
    return null
  }, [activeThread?.worker_jobs])

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
        annotations: Array.isArray(payload.annotations) ? payload.annotations : [],
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
    const submittedText = composerText.trim()
    clearComposer()
    setChatBusy(true)
    setChatError(null)
    try {
      await onSendChatMessage(activeThreadId, {
        message: submittedText,
        context_snapshot: onBuildViewerContext(),
      })
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'Chat request failed')
    } finally {
      setChatBusy(false)
    }
  }

  const commitLatestWorkerJob = async () => {
    const targetThreadId = activeThreadId || commitCandidate?.thread_id
    if (!targetThreadId || !commitCandidate || !onCommitWorkerJob) return
    setCommitBusy(true)
    setCommitError(null)
    try {
      await onCommitWorkerJob(targetThreadId, commitCandidate.job_id)
    } catch (error) {
      setCommitError(error instanceof Error ? error.message : 'Commit failed')
    } finally {
      setCommitBusy(false)
    }
  }

  const visualEvidenceForEvent = (event: DesignThreadEvent) => {
    if (event.type !== 'assistant_message' && event.type !== 'tool_result') return []
    const artifactId = event.metadata?.visual_evidence_artifact_id
    if (typeof artifactId !== 'string' || !artifactId.trim()) return []
    const artifact = visualEvidenceById.get(artifactId)
    return artifact ? [artifact] : []
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
                {commitCandidate && onCommitWorkerJob ? (
                  <button
                    type="button"
                    className="btn-tool"
                    onClick={() => void commitLatestWorkerJob()}
                    disabled={commitBusy || chatBusy || threadBusy}
                    aria-label="Commit worker job changes"
                  >
                    {commitBusy ? 'Committing...' : `Commit ${commitCandidate.changed_paths?.length ?? 0}`}
                  </button>
                ) : null}
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
            {commitError ? <span className="thread-error chat-composer-error">{commitError}</span> : null}

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

            <div className="chat-message-list" aria-label="Message history">
              {events.length ? (
                events.map((event) => {
                  const inlineEvidence = visualEvidenceForEvent(event)
                  return (
                    <article key={event.message_id} className={`chat-message chat-message-${event.role ?? event.type}`}>
                      <div className="chat-message-avatar">{eventActor(event)}</div>
                      <div className="chat-message-bubble">
                        <div className="chat-message-meta">
                          <span>{event.type}</span>
                          <span>{event.created_at ?? ''}</span>
                        </div>
                        {eventBody(event)}
                        {inlineEvidence.length ? (
                          <div className="chat-inline-evidence-list" aria-label="Assistant shared images">
                            {inlineEvidence.map((artifact) => {
                              const imageHref = artifact.image_url || artifact.image_endpoint || artifact.path
                              return imageHref ? (
                                <figure key={artifact.artifact_id} className="chat-inline-evidence">
                                  <img src={imageHref} alt={`Visual evidence ${artifact.view}`} />
                                  <figcaption>
                                    <span>{artifact.view} evidence</span>
                                    {artifact.width != null && artifact.height != null ? (
                                      <span>{artifact.width}x{artifact.height}</span>
                                    ) : null}
                                  </figcaption>
                                </figure>
                              ) : null
                            })}
                          </div>
                        ) : null}
                        {event.metadata?.context_snapshot_id ? (
                          <div className="context-pill chat-snapshot-pill">view {String(event.metadata.context_snapshot_id)}</div>
                        ) : null}
                      </div>
                    </article>
                  )
                })
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
              {chatError ? <span className="thread-error chat-composer-error">{chatError}</span> : null}
            </form>

            <details className="advanced-thread-tools">
              <summary>Advanced</summary>
              <div className="advanced-thread-section">
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
                  <button
                    type="button"
                    className={`btn-tool ${visualEvidenceFollowMode ? 'active' : ''}`}
                    aria-pressed={visualEvidenceFollowMode}
                    onClick={() => onVisualEvidenceFollowModeChange(!visualEvidenceFollowMode)}
                    disabled={!activeThreadId || isThreadMuted}
                  >
                    Follow mode
                  </button>
                  <div className="visual-evidence-request-status" aria-label="Visual evidence request status">
                    <span className="context-pill">pending: {requestStatusCounts.pending}</span>
                    <span className="context-pill">rendering: {requestStatusCounts.inFlight}</span>
                    <span className="context-pill">failed: {requestStatusCounts.failed}</span>
                    {typeof threadVisualEvidenceRequestCount === 'number' ? (
                      <span className="context-pill">requests: {threadVisualEvidenceRequestCount}</span>
                    ) : null}
                  </div>
                  {visualEvidenceError ? <span className="thread-error">{visualEvidenceError}</span> : null}
                  {recentVisualEvidenceRequests.length ? (
                    <ul className="visual-evidence-request-list" role="list" aria-label="Recent visual evidence requests">
                      {recentVisualEvidenceRequests.map((request) => (
                        <li key={request.request_id} className="visual-evidence-request-item" role="listitem">
                          <span className="context-pill">status: {request.status}</span>
                          <span className="context-pill">view: {request.view}</span>
                          {request.purpose ? <span className="context-pill">purpose: {request.purpose}</span> : null}
                          {request.artifact_id ? <span className="context-pill">artifact: {request.artifact_id}</span> : null}
                          {request.error ? <span className="thread-error">{request.error}</span> : null}
                          <span className="context-pill">id: {request.request_id}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
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
                              <>
                                <img
                                  className="visual-evidence-preview"
                                  src={imageHref}
                                  alt={`Visual evidence ${artifact.view}`}
                                />
                                <a className="btn-tool visual-evidence-link" href={imageHref} target="_blank" rel="noreferrer">
                                  Open image
                                </a>
                              </>
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
              </div>
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

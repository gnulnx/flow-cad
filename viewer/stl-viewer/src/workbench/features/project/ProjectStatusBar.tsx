import { useEffect, useState } from 'react'
import type { ChatProviderStatus, ProjectSummary, WorkbenchClient } from '../../contracts'
import { CodexConnectionSettings } from './CodexConnectionSettings'

interface ProjectStatusBarProps {
  client: WorkbenchClient
  onProjectChange(project: ProjectSummary | null): void
  chatProviderStatus?: ChatProviderStatus | null
  onRetryChatProvider?(): void
  refreshToken?: number
}

export function ProjectStatusBar({ client, onProjectChange, chatProviderStatus = null, onRetryChatProvider = () => undefined, refreshToken = 0 }: ProjectStatusBarProps) {
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    client.getProject(controller.signal).then((nextProject) => {
      setProject(nextProject)
      setError(null)
      onProjectChange(nextProject)
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      setError(reason instanceof Error ? reason.message : 'Project metadata unavailable')
      onProjectChange(null)
    })
    return () => controller.abort()
  }, [client, onProjectChange, refreshToken])

  return (
    <header className="project-status-bar">
      <div className="project-wordmark" aria-label="Flow CAD Workbench">
        <span className="project-wordmark__mark" aria-hidden="true">F</span>
        <span>
          <strong>Flow CAD</strong>
          <small>Workbench</small>
        </span>
      </div>
      {project ? (
        <div className="project-status-bar__identity">
          <strong>{project.projectName}</strong>
          <span>revision {project.revision}</span>
          <span>{project.activeAssemblyId ?? 'No active assembly'}</span>
        </div>
      ) : (
        <div className="project-status-bar__identity" aria-live="polite">
          <strong>{error ? 'Project unavailable' : 'Opening project…'}</strong>
          <span>{error ?? 'Metadata first; geometry follows'}</span>
        </div>
      )}
      <div className="project-status-bar__health">
        <span className={`health-dot ${error ? 'health-dot--error' : project ? 'health-dot--ready' : ''}`} />
        <span>{error ? 'Disconnected' : project ? 'Ready' : 'Connecting'}</span>
        {project?.gitCommit ? <code>{project.gitCommit.slice(0, 8)}{project.gitDirty ? '*' : ''}</code> : null}
        <button type="button" className="settings-button" onClick={() => setSettingsOpen(true)}>Settings</button>
      </div>
      {settingsOpen ? <CodexConnectionSettings status={chatProviderStatus} onRetry={onRetryChatProvider} onClose={() => setSettingsOpen(false)} /> : null}
    </header>
  )
}

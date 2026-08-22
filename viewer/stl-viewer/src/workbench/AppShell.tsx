import { useCallback, useMemo, useState } from 'react'
import { configuredWorkbenchClient } from './client'
import type { ProjectSummary, WorkbenchClient, WorkbenchPart } from './contracts'
import { ChatDock } from './features/chat/ChatDock'
import { PartInventoryDock } from './features/inventory/PartInventoryDock'
import { InspectorDock } from './features/inspector/InspectorDock'
import { JobDrawer } from './features/jobs/JobDrawer'
import { ProjectStatusBar } from './features/project/ProjectStatusBar'
import { WorkbenchViewport } from './features/viewport/WorkbenchViewport'
import './workbench.css'

interface AppShellProps {
  client?: WorkbenchClient
}

export default function AppShell({ client }: AppShellProps) {
  const workbenchClient = useMemo(() => client ?? configuredWorkbenchClient(), [client])
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [activePart, setActivePart] = useState<WorkbenchPart | null>(null)
  const [visiblePartUuids, setVisiblePartUuids] = useState<string[]>([])
  const selectPart = useCallback((part: WorkbenchPart) => setActivePart(part), [])
  const projectChanged = useCallback((nextProject: ProjectSummary | null) => setProject(nextProject), [])
  const visibilityChanged = useCallback((partUuid: string, visible: boolean) => {
    setVisiblePartUuids((current) => visible
      ? current.includes(partUuid) ? current : [...current, partUuid]
      : current.filter((uuid) => uuid !== partUuid))
  }, [])

  return (
    <div className="workbench-shell">
      <ProjectStatusBar client={workbenchClient} onProjectChange={projectChanged} />
      <div className="workbench-shell__body">
        <aside className="left-workbench-dock">
          <PartInventoryDock
            client={workbenchClient}
            activePartUuid={activePart?.uuid ?? null}
            onSelect={selectPart}
          />
          <InspectorDock part={activePart} />
        </aside>
        <main className="workbench-main">
          <WorkbenchViewport
            client={workbenchClient}
            part={activePart}
            backendRevision={project?.revision ?? null}
            onVisibilityChange={visibilityChanged}
          />
          <JobDrawer client={workbenchClient} />
        </main>
        <ChatDock
          client={workbenchClient}
          available={project?.chatAvailable ?? true}
          context={{
            projectRevision: project?.revision ?? null,
            selectedPartUuid: activePart?.uuid ?? null,
            selectedPartKey: activePart?.key ?? null,
            visibleOccurrenceIds: activePart && visiblePartUuids.includes(activePart.uuid) ? activePart.occurrenceIds : [],
            artifactHashes: activePart
              ? {
                  ...(activePart.authorityHash ? { [activePart.uuid]: activePart.authorityHash } : {}),
                  ...(activePart.displayArtifact ? { [`${activePart.uuid}:display`]: activePart.displayArtifact.contentHash } : {}),
                }
              : {},
          }}
        />
      </div>
    </div>
  )
}

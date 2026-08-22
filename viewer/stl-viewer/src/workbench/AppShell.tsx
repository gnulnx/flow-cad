import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { configuredWorkbenchClient } from './client'
import type { ProjectSummary, WorkbenchClient, WorkbenchPart } from './contracts'
import { ChatDock } from './features/chat/ChatDock'
import { PartInventoryDock } from './features/inventory/PartInventoryDock'
import { InspectorDock } from './features/inspector/InspectorDock'
import { JobDrawer } from './features/jobs/JobDrawer'
import type { MeasurementResult } from './features/measurement/measurement'
import { measurementFingerprint, restoredMeasurements, savedLabels } from './features/measurement/persistence'
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
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [visiblePartUuids, setVisiblePartUuids] = useState<string[]>([])
  const [measurementRestore, setMeasurementRestore] = useState<{ key: string; measurements: MeasurementResult[] } | null>(null)
  const [measurementSaveError, setMeasurementSaveError] = useState<string | null>(null)
  const savedMeasurementFingerprint = useRef<{ key: string; fingerprint: string } | null>(null)
  const measurementSaveTimer = useRef<number | null>(null)
  const selectPart = useCallback((part: WorkbenchPart) => setActivePart(part), [])
  const projectChanged = useCallback((nextProject: ProjectSummary | null) => setProject(nextProject), [])
  const visibilityChanged = useCallback((partUuid: string, visible: boolean) => {
    setVisiblePartUuids((current) => visible
      ? current.includes(partUuid) ? current : [...current, partUuid]
      : current.filter((uuid) => uuid !== partUuid))
  }, [])
  const measurementKey = activeThreadId && activePart?.authorityHash
    ? `${activeThreadId}:${activePart.uuid}:${activePart.authorityHash}`
    : null

  useEffect(() => {
    if (measurementSaveTimer.current !== null) window.clearTimeout(measurementSaveTimer.current)
    measurementSaveTimer.current = null
    setMeasurementSaveError(null)
    if (!measurementKey || !activeThreadId || !activePart) {
      savedMeasurementFingerprint.current = null
      setMeasurementRestore(null)
      return
    }
    const key = measurementKey
    const empty: MeasurementResult[] = []
    savedMeasurementFingerprint.current = { key, fingerprint: measurementFingerprint(empty) }
    setMeasurementRestore({ key, measurements: empty })
    const controller = new AbortController()
    workbenchClient.getLatestMeasurementSnapshot(activeThreadId, activePart.uuid, controller.signal)
      .then((snapshot) => {
        const measurements = restoredMeasurements(snapshot)
        savedMeasurementFingerprint.current = { key, fingerprint: measurementFingerprint(measurements) }
        setMeasurementRestore({ key, measurements })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setMeasurementSaveError(error instanceof Error ? error.message : String(error))
      })
    return () => controller.abort()
  }, [activePart, activeThreadId, measurementKey, workbenchClient])

  useEffect(() => () => {
    if (measurementSaveTimer.current !== null) window.clearTimeout(measurementSaveTimer.current)
  }, [])

  const measurementsChanged = useCallback((measurements: MeasurementResult[]) => {
    if (!measurementKey || !measurementRestore || measurementRestore.key !== measurementKey || !activeThreadId || !activePart?.authorityHash) return
    const currentArtifactRevision = activePart.authorityHash
    const fingerprint = measurementFingerprint(measurements)
    if (savedMeasurementFingerprint.current?.key === measurementKey
      && savedMeasurementFingerprint.current.fingerprint === fingerprint) return
    const revisions = new Set(measurements.map((measurement) => measurement.binding.artifactRevision))
    if (revisions.size > 1) {
      setMeasurementSaveError('Measurements span artifact revisions; clear stale labels before saving new measurements.')
      return
    }
    if (measurementSaveTimer.current !== null) window.clearTimeout(measurementSaveTimer.current)
    measurementSaveTimer.current = window.setTimeout(() => {
      const artifactRevision = revisions.values().next().value ?? currentArtifactRevision
      workbenchClient.saveMeasurementSnapshot({
        requestId: crypto.randomUUID(),
        threadId: activeThreadId,
        partUuid: activePart.uuid,
        artifactRevision,
        measurements: savedLabels(measurements),
      }).then(() => {
        savedMeasurementFingerprint.current = { key: measurementKey, fingerprint }
        setMeasurementSaveError(null)
      }).catch((error: unknown) => {
        setMeasurementSaveError(error instanceof Error ? error.message : String(error))
      })
    }, 250)
  }, [activePart, activeThreadId, measurementKey, measurementRestore, workbenchClient])

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
            threadId={activeThreadId}
            onVisibilityChange={visibilityChanged}
            measurementRestore={measurementRestore}
            onMeasurementsChange={measurementsChanged}
          />
          {measurementSaveError ? <p className="measurement-save-error" role="status">{measurementSaveError}</p> : null}
          <JobDrawer client={workbenchClient} />
        </main>
        <ChatDock
          client={workbenchClient}
          available={project?.chatAvailable ?? true}
          onThreadChange={setActiveThreadId}
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

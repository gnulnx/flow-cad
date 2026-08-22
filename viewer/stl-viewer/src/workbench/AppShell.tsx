import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { configuredWorkbenchClient } from './client'
import type { InventorySnapshot, ProjectSummary, WorkbenchClient, WorkbenchJob, WorkbenchPart } from './contracts'
import { ChatDock } from './features/chat/ChatDock'
import { PartInventoryDock } from './features/inventory/PartInventoryDock'
import { InspectorDock } from './features/inspector/InspectorDock'
import { JobDrawer } from './features/jobs/JobDrawer'
import type { MeasurementResult } from './features/measurement/measurement'
import { measurementFingerprint, restoredMeasurements, savedLabels } from './features/measurement/persistence'
import { ProjectStatusBar } from './features/project/ProjectStatusBar'
import { WorkbenchViewport, type AssemblyViewportSnapshot } from './features/viewport/WorkbenchViewport'
import type { WorkbenchViewportContext } from './features/viewport/viewportContext'
import './workbench.css'

interface AppShellProps {
  client?: WorkbenchClient
}

const EMPTY_PARTS: WorkbenchPart[] = []

export default function AppShell({ client }: AppShellProps) {
  const workbenchClient = useMemo(() => client ?? configuredWorkbenchClient(), [client])
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [inventory, setInventory] = useState<InventorySnapshot | null>(null)
  const [activePart, setActivePart] = useState<WorkbenchPart | null>(null)
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [chatProviderAvailable, setChatProviderAvailable] = useState<boolean | null>(null)
  const [chatMeasurements, setChatMeasurements] = useState<MeasurementResult[]>([])
  const [viewportContext, setViewportContext] = useState<WorkbenchViewportContext | null>(null)
  const [watchedBuildJobId, setWatchedBuildJobId] = useState<string | null>(null)
  const [inventoryRefreshToken, setInventoryRefreshToken] = useState(0)
  const [chatDraftRequest, setChatDraftRequest] = useState<{ id: string, content: string } | null>(null)
  const [assemblyState, setAssemblyState] = useState<AssemblyViewportSnapshot>({
    partStates: {},
    visibleOccurrenceIds: [],
    artifactHashes: {},
  })
  const [measurementRestore, setMeasurementRestore] = useState<{ key: string; measurements: MeasurementResult[] } | null>(null)
  const [measurementSaveError, setMeasurementSaveError] = useState<string | null>(null)
  const savedMeasurementFingerprint = useRef<{ key: string; fingerprint: string } | null>(null)
  const measurementSaveTimer = useRef<number | null>(null)
  const selectPart = useCallback((part: WorkbenchPart) => setActivePart(part), [])
  const projectChanged = useCallback((nextProject: ProjectSummary | null) => setProject(nextProject), [])
  const inventoryChanged = useCallback((snapshot: InventorySnapshot) => setInventory(snapshot), [])
  const assemblyChanged = useCallback((snapshot: AssemblyViewportSnapshot) => setAssemblyState(snapshot), [])
  const buildSubmitted = useCallback((jobId: string) => setWatchedBuildJobId(jobId), [])
  const buildFinished = useCallback((job: WorkbenchJob) => {
    setWatchedBuildJobId(null)
    if (job.state === 'complete') setInventoryRefreshToken((value) => value + 1)
  }, [])
  const askAgentAboutMarkup = useCallback(() => {
    setChatDraftRequest({
      id: crypto.randomUUID(),
      content: 'Review the attached viewport markup and explain what geometry change it indicates.',
    })
  }, [])
  const measurementKey = activeThreadId && activePart?.authorityHash
    ? `${activeThreadId}:${activePart.uuid}:${activePart.authorityHash}`
    : null

  useEffect(() => {
    const controller = new AbortController()
    workbenchClient.getChatProvider(controller.signal)
      .then((provider) => setChatProviderAvailable(provider.available))
      .catch(() => {
        if (!controller.signal.aborted) setChatProviderAvailable(false)
      })
    return () => controller.abort()
  }, [workbenchClient])

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
    setChatMeasurements(measurements)
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
      <ProjectStatusBar client={workbenchClient} onProjectChange={projectChanged} refreshToken={inventoryRefreshToken} />
      <div className="workbench-shell__body">
        <aside className="left-workbench-dock">
          <PartInventoryDock
            client={workbenchClient}
            activePartUuid={activePart?.uuid ?? null}
            onSelect={selectPart}
            onInventoryChange={inventoryChanged}
            loadStates={assemblyState.partStates}
            refreshToken={inventoryRefreshToken}
          />
          <InspectorDock client={workbenchClient} part={activePart} onBuildSubmitted={buildSubmitted} />
        </aside>
        <main className="workbench-main">
          <WorkbenchViewport
            client={workbenchClient}
            parts={inventory?.parts ?? EMPTY_PARTS}
            part={activePart}
            activeAssemblyId={project?.activeAssemblyId ?? inventory?.activeAssemblyId ?? null}
            backendRevision={project?.revision ?? null}
            threadId={activeThreadId}
            onAssemblyStateChange={assemblyChanged}
            measurementRestore={measurementRestore}
            onMeasurementsChange={measurementsChanged}
            onViewportContextChange={setViewportContext}
            onAskAgentAboutMarkup={askAgentAboutMarkup}
          />
          {measurementSaveError ? <p className="measurement-save-error" role="status">{measurementSaveError}</p> : null}
          <JobDrawer client={workbenchClient} watchJobId={watchedBuildJobId} onWatchedJobTerminal={buildFinished} />
        </main>
        <ChatDock
          client={workbenchClient}
          available={chatProviderAvailable ?? project?.chatAvailable ?? false}
          onThreadChange={setActiveThreadId}
          draftRequest={chatDraftRequest}
          context={{
            projectRevision: project?.revision ?? null,
            selectedPartUuid: activePart?.uuid ?? null,
            selectedPartKey: activePart?.key ?? null,
            visibleOccurrenceIds: assemblyState.visibleOccurrenceIds,
            artifactHashes: {
              ...assemblyState.artifactHashes,
              ...(activePart?.authorityHash ? { [`${activePart.uuid}:authority`]: activePart.authorityHash } : {}),
            },
            camera: viewportContext?.camera as unknown as Record<string, unknown> ?? {},
            measurements: savedLabels(viewportContext?.measurements ?? chatMeasurements) as unknown as Record<string, unknown>[],
            annotations: viewportContext ? [{
              hidden: viewportContext.annotations.hidden,
              marks: viewportContext.annotations.marks,
            }] as unknown as Record<string, unknown>[] : [],
            viewportAttachment: viewportContext?.latestCapture as unknown as Record<string, unknown> ?? null,
          }}
        />
      </div>
    </div>
  )
}

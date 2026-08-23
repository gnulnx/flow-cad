import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { configuredWorkbenchClient } from './client'
import type { ChatProviderStatus, InventorySnapshot, ProjectSummary, WorkbenchClient, WorkbenchJob, WorkbenchPart } from './contracts'
import { ChatDock } from './features/chat/ChatDock'
import { PartInventoryDock } from './features/inventory/PartInventoryDock'
import { applyPartSelection, type PartSelectionMode, type PartSelectionState } from './features/inventory/selection'
import { InspectorDock } from './features/inspector/InspectorDock'
import { JobDrawer } from './features/jobs/JobDrawer'
import type { MeasurementResult } from './features/measurement/measurement'
import { measurementFingerprint, restoredMeasurements, savedLabels } from './features/measurement/persistence'
import { ProjectStatusBar } from './features/project/ProjectStatusBar'
import { WorkbenchViewport, type AssemblyViewportSnapshot } from './features/viewport/WorkbenchViewport'
import { planAssemblyLoads } from './features/viewport/assembly'
import type { WorkbenchViewportContext } from './features/viewport/viewportContext'
import './workbench.css'

interface AppShellProps {
  client?: WorkbenchClient
}

const EMPTY_PARTS: WorkbenchPart[] = []
const PROJECT_METADATA_POLL_MS = 1_000

function projectStateKey(project: ProjectSummary | null): string | null {
  return project ? `${project.revision}:${project.viewStateRevision ?? 'none'}` : null
}

export default function AppShell({ client }: AppShellProps) {
  const workbenchClient = useMemo(() => client ?? configuredWorkbenchClient(), [client])
  const [project, setProject] = useState<ProjectSummary | null>(null)
  const [inventory, setInventory] = useState<InventorySnapshot | null>(null)
  const [selection, setSelection] = useState<PartSelectionState>({
    activePartUuid: null,
    explicitVisiblePartUuids: null,
  })
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [chatProviderStatus, setChatProviderStatus] = useState<ChatProviderStatus | null>(null)
  const [chatProviderRefreshToken, setChatProviderRefreshToken] = useState(0)
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
  const [projectBuildSubmitting, setProjectBuildSubmitting] = useState(false)
  const [projectActionError, setProjectActionError] = useState<string | null>(null)
  const [fitAssemblyRequest, setFitAssemblyRequest] = useState(0)
  const observedProjectState = useRef<string | null>(null)
  const savedMeasurementFingerprint = useRef<{ key: string; fingerprint: string } | null>(null)
  const measurementSaveTimer = useRef<number | null>(null)
  const parts = inventory?.parts ?? EMPTY_PARTS
  const activeAssemblyId = project?.activeAssemblyId ?? inventory?.activeAssemblyId ?? null
  const defaultVisiblePartUuids = useMemo(
    () => planAssemblyLoads(parts, activeAssemblyId, null).map((item) => item.part.uuid),
    [activeAssemblyId, parts],
  )
  const visiblePartUuids = selection.explicitVisiblePartUuids ?? defaultVisiblePartUuids
  const activePart = parts.find((part) => part.uuid === selection.activePartUuid) ?? null
  const selectPart = useCallback((part: WorkbenchPart, mode: PartSelectionMode) => {
    const effectiveMode = part.previewOfUuid && mode === 'replace' ? 'focus' : mode
    setSelection((current) => applyPartSelection(current, part.uuid, effectiveMode, defaultVisiblePartUuids))
  }, [defaultVisiblePartUuids])
  const projectChanged = useCallback((nextProject: ProjectSummary | null) => {
    observedProjectState.current = projectStateKey(nextProject)
    setProject(nextProject)
  }, [])
  const inventoryChanged = useCallback((snapshot: InventorySnapshot) => setInventory(snapshot), [])
  const assemblyChanged = useCallback((snapshot: AssemblyViewportSnapshot) => setAssemblyState(snapshot), [])
  const buildSubmitted = useCallback((jobId: string) => setWatchedBuildJobId(jobId), [])
  const buildFinished = useCallback((job: WorkbenchJob) => {
    setWatchedBuildJobId(null)
    if (job.state === 'complete') setInventoryRefreshToken((value) => value + 1)
  }, [])
  const buildRobot = useCallback(async () => {
    if (projectBuildSubmitting) return
    setProjectBuildSubmitting(true)
    setProjectActionError(null)
    try {
      const job = await workbenchClient.buildProject(crypto.randomUUID())
      setWatchedBuildJobId(job.id)
    } catch (error: unknown) {
      setProjectActionError(error instanceof Error ? error.message : String(error))
    } finally {
      setProjectBuildSubmitting(false)
    }
  }, [projectBuildSubmitting, workbenchClient])
  const showFullyAssembled = useCallback(async () => {
    setProjectActionError(null)
    try {
      await workbenchClient.clearPreview()
    } catch (error: unknown) {
      setProjectActionError(error instanceof Error ? error.message : String(error))
      return
    }
    setSelection({ activePartUuid: null, explicitVisiblePartUuids: null })
    setInventoryRefreshToken((value) => value + 1)
    setFitAssemblyRequest((value) => value + 1)
  }, [workbenchClient])
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
      .then(setChatProviderStatus)
      .catch(() => {
        if (!controller.signal.aborted) setChatProviderStatus({ provider: null, available: false, status: 'unavailable' })
      })
    return () => controller.abort()
  }, [chatProviderRefreshToken, workbenchClient])

  useEffect(() => {
    let stopped = false
    let controller: AbortController | null = null
    const poll = () => {
      controller?.abort()
      controller = new AbortController()
      workbenchClient.getProject(controller.signal).then((nextProject) => {
        if (stopped) return
        const nextState = projectStateKey(nextProject)
        if (observedProjectState.current === null) {
          observedProjectState.current = nextState
          return
        }
        if (nextState !== observedProjectState.current) {
          observedProjectState.current = nextState
          setProject(nextProject)
          setInventoryRefreshToken((value) => value + 1)
        }
      }).catch(() => undefined)
    }
    const interval = window.setInterval(poll, PROJECT_METADATA_POLL_MS)
    return () => {
      stopped = true
      controller?.abort()
      window.clearInterval(interval)
    }
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
      <ProjectStatusBar
        client={workbenchClient}
        onProjectChange={projectChanged}
        chatProviderStatus={chatProviderStatus}
        onRetryChatProvider={() => {
          setChatProviderStatus(null)
          setChatProviderRefreshToken((value) => value + 1)
        }}
        refreshToken={inventoryRefreshToken}
      />
      <div className="workbench-shell__body">
        <aside className="left-workbench-dock">
          <PartInventoryDock
            client={workbenchClient}
            activePartUuid={activePart?.uuid ?? null}
            visiblePartUuids={visiblePartUuids}
            onSelect={selectPart}
            onInventoryChange={inventoryChanged}
            loadStates={assemblyState.partStates}
            refreshToken={inventoryRefreshToken}
            onShowFullyAssembled={() => void showFullyAssembled()}
            onBuildRobot={() => void buildRobot()}
            buildRobotSubmitting={projectBuildSubmitting}
            actionError={projectActionError}
          />
          <InspectorDock client={workbenchClient} part={activePart} onBuildSubmitted={buildSubmitted} />
        </aside>
        <main className="workbench-main">
          <WorkbenchViewport
            client={workbenchClient}
            parts={inventory?.parts ?? EMPTY_PARTS}
            part={activePart}
            visiblePartUuids={visiblePartUuids}
            activeAssemblyId={activeAssemblyId}
            backendRevision={project?.revision ?? null}
            threadId={activeThreadId}
            onAssemblyStateChange={assemblyChanged}
            measurementRestore={measurementRestore}
            onMeasurementsChange={measurementsChanged}
            onViewportContextChange={setViewportContext}
            onAskAgentAboutMarkup={askAgentAboutMarkup}
            fitAssemblyRequest={fitAssemblyRequest}
          />
          {measurementSaveError ? <p className="measurement-save-error" role="status">{measurementSaveError}</p> : null}
          <JobDrawer client={workbenchClient} watchJobId={watchedBuildJobId} onWatchedJobTerminal={buildFinished} />
        </main>
        <ChatDock
          client={workbenchClient}
          available={chatProviderStatus?.available ?? project?.chatAvailable ?? false}
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

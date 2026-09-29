import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ArtifactState, WorkbenchOccurrence, WorkbenchPart } from '../../contracts'
import { cachedDisplayBytes, loadDisplayBytes, type DisplayBytes } from './displayScene'
import {
  nextAssemblyLoadBatch,
  partLoadStates,
  planAssemblyLoads,
  reconcileLoadRecords,
  type AssemblyLoadRecords,
} from './assembly'

export const ASSEMBLY_LOAD_CONCURRENCY = 3

export interface LoadedAssemblyPart {
  key: string
  part: WorkbenchPart
  occurrences: WorkbenchOccurrence[]
  artifactBytes: ArrayBuffer
  format?: 'stl' | 'glb'
  displayWarning?: string | null
}

export interface AssemblyDisplayProgress {
  total: number
  queued: number
  loading: number
  visible: number
  failed: number
}

export interface AssemblyDisplayState {
  models: LoadedAssemblyPart[]
  partStates: Record<string, ArtifactState>
  visibleOccurrenceIds: string[]
  artifactHashes: Record<string, string>
  progress: AssemblyDisplayProgress
  selectedOccurrence: WorkbenchOccurrence | null
  reportVisible(partUuid: string): void
  reportParseFailure(partUuid: string, message: string): void
}

export function useAssemblyDisplayQueue(
  parts: WorkbenchPart[],
  activeAssemblyId: string | null,
  selectedPartUuid: string | null,
  visiblePartUuids: readonly string[] | null = null,
  concurrency = ASSEMBLY_LOAD_CONCURRENCY,
): AssemblyDisplayState {
  const plan = useMemo(
    () => planAssemblyLoads(parts, activeAssemblyId, selectedPartUuid, visiblePartUuids),
    [activeAssemblyId, parts, selectedPartUuid, visiblePartUuids],
  )
  const planKey = plan.map((item) => item.key).join('|')
  const planRef = useRef(plan)
  const controllersRef = useRef(new Map<string, AbortController>())
  const [records, setRecords] = useState<AssemblyLoadRecords>({})
  const [bytes, setBytes] = useState<Record<string, DisplayBytes>>({})

  planRef.current = plan

  useEffect(() => {
    const desired = new Set(plan.map((item) => item.key))
    const restored = Object.fromEntries(plan.flatMap((item) => {
      const cached = cachedDisplayBytes(item.part)
      return cached ? [[item.key, cached]] : []
    }))
    setBytes((current) => ({
      ...Object.fromEntries(Object.entries(current).filter(([key]) => desired.has(key))), ...restored,
    }))
    const aborted: string[] = []
    for (const [key, controller] of controllersRef.current) {
      if (!desired.has(key)) {
        controller.abort()
        controllersRef.current.delete(key)
        aborted.push(key)
      }
    }
    setRecords((current) => {
      const reset = Object.fromEntries(Object.entries(current).filter(([key]) => desired.has(key)))
      aborted.forEach((key) => {
        const record = reset[key]
        if (record?.state === 'loading') reset[key] = { ...record, state: 'queued', error: null }
      })
      const next = reconcileLoadRecords(reset, plan)
      for (const key of Object.keys(restored)) {
        if (next[key]?.state === 'queued') next[key] = { ...next[key], state: 'downloaded', error: null }
      }
      return next
    })
  }, [planKey]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const batch = nextAssemblyLoadBatch(plan, records, concurrency)
      .filter((item) => !controllersRef.current.has(item.key) && !cachedDisplayBytes(item.part))
    if (batch.length === 0) return
    setRecords((current) => {
      const next = { ...current }
      batch.forEach((item) => {
        const record = next[item.key]
        if (record?.state === 'queued') next[item.key] = { ...record, state: 'loading', error: null }
      })
      return next
    })
    batch.forEach((item) => {
      const controller = new AbortController()
      controllersRef.current.set(item.key, controller)
      loadDisplayBytes(item.part, controller.signal, item.priority === 0).then((artifactBytes) => {
        if (controller.signal.aborted) return
        setBytes((current) => ({ ...current, [item.key]: artifactBytes }))
        setRecords((current) => ({
          ...current,
          [item.key]: { ...current[item.key], state: current[item.key]?.state === 'visible' ? 'visible' : 'downloaded', error: null },
        }))
      }).catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setRecords((current) => ({
          ...current,
          [item.key]: {
            ...current[item.key],
            state: 'failed',
            error: reason instanceof Error ? reason.message : 'Display artifact could not be loaded',
          },
        }))
      }).finally(() => {
        if (controllersRef.current.get(item.key) === controller) controllersRef.current.delete(item.key)
      })
    })
  }, [concurrency, plan, records])

  useEffect(() => () => {
    controllersRef.current.forEach((controller) => controller.abort())
    controllersRef.current.clear()
  }, [])

  const models = useMemo(() => plan.flatMap((item) => {
    const loaded = bytes[item.key]
    return (records[item.key]?.state === 'downloaded' || records[item.key]?.state === 'visible') && loaded
      ? [{ ...item, artifactBytes: loaded.artifactBytes, format: loaded.format, displayWarning: loaded.warning,
        part: { ...item.part, displayArtifact: { ...item.part.displayArtifact!, contentHash: loaded.hash, format: loaded.format } } }]
      : []
  }), [bytes, plan, records])
  const progress = useMemo(() => plan.reduce<AssemblyDisplayProgress>((summary, item) => {
    const state = records[item.key]?.state ?? 'queued'
    summary[state === 'downloaded' ? 'loading' : state] += 1
    summary.total += 1
    return summary
  }, { total: 0, queued: 0, loading: 0, visible: 0, failed: 0 }), [plan, records])
  const reportParseFailure = useCallback((partUuid: string, message: string) => {
    const item = planRef.current.find((candidate) => candidate.part.uuid === partUuid)
    if (!item) return
    setRecords((current) => ({
      ...current,
      [item.key]: { ...current[item.key], state: 'failed', error: message },
    }))
  }, [])
  const reportVisible = useCallback((partUuid: string) => {
    const item = planRef.current.find((candidate) => candidate.part.uuid === partUuid)
    if (!item) return
    setRecords((current) => current[item.key]?.state === 'downloaded' ? {
      ...current,
      [item.key]: { ...current[item.key], state: 'visible', error: null },
    } : current)
  }, [])
  const visibleOccurrenceIds = useMemo(
    () => models.flatMap((model) => model.occurrences.map((occurrence) => occurrence.id)),
    [models],
  )
  const artifactHashes = useMemo(
    () => Object.fromEntries(models.map((model) => [model.part.uuid, model.part.displayArtifact!.contentHash])),
    [models],
  )
  const loadStates = useMemo(() => partLoadStates(plan, records), [plan, records])

  return {
    models,
    partStates: loadStates,
    visibleOccurrenceIds,
    artifactHashes,
    progress,
    selectedOccurrence: plan.find((item) => item.part.uuid === selectedPartUuid)?.occurrences[0] ?? null,
    reportVisible,
    reportParseFailure,
  }
}

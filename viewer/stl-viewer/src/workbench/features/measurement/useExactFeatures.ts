import { useEffect, useState } from 'react'
import type { ExactFeatureSet, WorkbenchClient } from '../../contracts'

export type ExactFeatureLoadState =
  | { status: 'idle'; featureSet: null; error: null }
  | { status: 'loading' | 'extracting'; featureSet: null; error: null }
  | { status: 'ready'; featureSet: ExactFeatureSet; error: null }
  | { status: 'failed'; featureSet: null; error: string }

const POLL_INTERVAL_MS = 125

export function useExactFeatures(
  client: WorkbenchClient,
  partUuid: string | null,
  artifactRevision: string | null,
  enabled: boolean,
): ExactFeatureLoadState {
  const [state, setState] = useState<ExactFeatureLoadState>({ status: 'idle', featureSet: null, error: null })

  useEffect(() => {
    const controller = new AbortController()
    if (!enabled || !partUuid || !artifactRevision) {
      setState({ status: 'idle', featureSet: null, error: null })
      return () => controller.abort()
    }

    const requestId = `exact-features:${partUuid}:${artifactRevision}`
    setState({ status: 'loading', featureSet: null, error: null })

    const load = async () => {
      try {
        let lookup = await client.getExactFeatures(partUuid, artifactRevision, controller.signal)
        if (lookup.status === 'job_required') {
          setState({ status: 'extracting', featureSet: null, error: null })
          const queued = await client.queueExactFeatures(partUuid, artifactRevision, requestId, controller.signal)
          if (queued.status === 'ready') {
            setState({ status: 'ready', featureSet: queued, error: null })
            return
          }
          while (!controller.signal.aborted) {
            await abortableDelay(POLL_INTERVAL_MS, controller.signal)
            lookup = await client.getExactFeatures(partUuid, artifactRevision, controller.signal)
            if (lookup.status === 'ready') break
            const jobs = await client.getJobs(controller.signal)
            const job = jobs.find((record) => record.id === queued.jobId)
            if (job?.state === 'failed' || job?.state === 'cancelled') {
              throw new Error(`Exact STEP extraction ${job.state}: ${job.phase}`)
            }
          }
        }
        if (!controller.signal.aborted && lookup.status === 'ready') {
          setState({ status: 'ready', featureSet: lookup, error: null })
        }
      } catch (reason) {
        if (controller.signal.aborted) return
        setState({
          status: 'failed',
          featureSet: null,
          error: reason instanceof Error ? reason.message : 'Exact STEP features could not be loaded',
        })
      }
    }

    void load()
    return () => controller.abort()
  }, [artifactRevision, client, enabled, partUuid])

  return state
}

function abortableDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(resolve, milliseconds)
    signal.addEventListener('abort', () => {
      window.clearTimeout(timeout)
      reject(new DOMException('Aborted', 'AbortError'))
    }, { once: true })
  })
}

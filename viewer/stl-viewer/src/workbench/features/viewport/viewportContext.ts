import { useEffect, useRef } from 'react'
import type { AnnotationMark } from '../annotation/contracts'
import type { MeasurementResult } from '../measurement/measurement'
import type { LiveCanvasCaptureMetadata, LiveViewportSource } from './agentScreen'

export interface WorkbenchViewportContext {
  camera: LiveViewportSource['camera'] | null
  measurements: MeasurementResult[]
  annotations: {
    marks: AnnotationMark[]
    hidden: boolean
  }
  latestCapture: LiveCanvasCaptureMetadata | null
}

interface ViewportContextEmitterOptions {
  getLiveViewport(): LiveViewportSource | null
  measurements: MeasurementResult[]
  annotationMarks: AnnotationMark[]
  annotationsHidden: boolean
  latestCapture: LiveCanvasCaptureMetadata | null
  onChange?(context: WorkbenchViewportContext): void
  debounceMs?: number
  pollMs?: number
}

export function useViewportContextEmitter({
  getLiveViewport,
  measurements,
  annotationMarks,
  annotationsHidden,
  latestCapture,
  onChange,
  debounceMs = 120,
  pollMs = 100,
}: ViewportContextEmitterOptions) {
  const valuesRef = useRef({ measurements, annotationMarks, annotationsHidden, latestCapture })
  const lastFingerprintRef = useRef('')
  valuesRef.current = { measurements, annotationMarks, annotationsHidden, latestCapture }

  useEffect(() => {
    if (!onChange) return
    let timer: number | null = null
    let pending: WorkbenchViewportContext | null = null
    let pendingFingerprint = ''
    const inspect = () => {
      const values = valuesRef.current
      const context: WorkbenchViewportContext = {
        camera: getLiveViewport()?.camera ?? null,
        measurements: values.measurements,
        annotations: { marks: values.annotationMarks, hidden: values.annotationsHidden },
        latestCapture: values.latestCapture,
      }
      const fingerprint = JSON.stringify(context)
      if (fingerprint === lastFingerprintRef.current || fingerprint === pendingFingerprint) return
      pending = context
      pendingFingerprint = fingerprint
      if (timer !== null) window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        if (!pending) return
        lastFingerprintRef.current = JSON.stringify(pending)
        onChange(pending)
        pending = null
        pendingFingerprint = ''
        timer = null
      }, debounceMs)
    }
    inspect()
    const interval = window.setInterval(inspect, pollMs)
    return () => {
      if (timer !== null) window.clearTimeout(timer)
      window.clearInterval(interval)
    }
  }, [debounceMs, getLiveViewport, onChange, pollMs])
}

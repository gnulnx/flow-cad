import type { SavedMeasurementLabel, SavedMeasurementSnapshot } from '../../contracts'
import type { MeasurementResult } from './measurement'

export function savedLabels(measurements: MeasurementResult[]): SavedMeasurementLabel[] {
  return measurements.map((measurement) => ({
    measurementId: measurement.id,
    kind: measurement.kind,
    title: measurement.title,
    quality: measurement.quality === 'Exact' ? 'exact' : 'approximate',
    startMm: measurement.startMm,
    endMm: measurement.endMm,
    totalMm: measurement.totalMm,
    deltaMm: measurement.deltaMm,
    featureIds: measurement.binding.featureIds,
    hidden: measurement.hidden,
    pinned: measurement.pinned,
    labelOffsetPx: measurement.offsetPx,
  }))
}

export function restoredMeasurements(snapshot: SavedMeasurementSnapshot | null): MeasurementResult[] {
  if (!snapshot) return []
  return snapshot.measurements.map((measurement) => ({
    id: measurement.measurementId,
    kind: measurement.kind,
    title: measurement.title,
    quality: measurement.quality === 'exact' ? 'Exact' : 'Approximate',
    startMm: measurement.startMm,
    endMm: measurement.endMm,
    totalMm: measurement.totalMm,
    deltaMm: measurement.deltaMm,
    binding: {
      partUuid: snapshot.partUuid,
      artifactRevision: snapshot.artifactRevision,
      featureIds: measurement.featureIds,
    },
    hidden: measurement.hidden,
    pinned: measurement.pinned,
    offsetPx: measurement.labelOffsetPx,
  }))
}

export function measurementFingerprint(measurements: MeasurementResult[]): string {
  return JSON.stringify(savedLabels(measurements))
}

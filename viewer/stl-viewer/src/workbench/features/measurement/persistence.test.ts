import { describe, expect, it } from 'vitest'
import type { SavedMeasurementSnapshot } from '../../contracts'
import { measurementFingerprint, restoredMeasurements, savedLabels } from './persistence'

const snapshot: SavedMeasurementSnapshot = {
  threadId: 'thread-1',
  partUuid: '11111111-1111-4111-8111-111111111111',
  artifactRevision: 'a'.repeat(64),
  measurements: [{
    measurementId: 'measurement-1',
    kind: 'distance',
    title: 'Exact vertex to Exact vertex',
    quality: 'exact',
    startMm: [1, 2, 3],
    endMm: [4, 6, 3],
    totalMm: 5,
    deltaMm: [3, 4, 0],
    featureIds: ['vertex-1', 'vertex-2'],
    hidden: true,
    pinned: true,
    labelOffsetPx: [12, -4],
  }],
}

describe('measurement persistence mapping', () => {
  it('round-trips revision-bound label state without geometry', () => {
    const restored = restoredMeasurements(snapshot)

    expect(restored[0].binding).toEqual({
      partUuid: snapshot.partUuid,
      artifactRevision: snapshot.artifactRevision,
      featureIds: ['vertex-1', 'vertex-2'],
    })
    expect(savedLabels(restored)).toEqual(snapshot.measurements)
  })

  it('uses a deterministic content fingerprint', () => {
    const restored = restoredMeasurements(snapshot)
    expect(measurementFingerprint(restored)).toBe(measurementFingerprint([...restored]))
    expect(measurementFingerprint([])).not.toBe(measurementFingerprint(restored))
  })
})

import { describe, expect, it } from 'vitest'
import type { WorkbenchOccurrence, WorkbenchPart } from '../../contracts'
import {
  nextAssemblyLoadBatch,
  planAssemblyLoads,
  reconcileLoadRecords,
  transformExactFeature,
  transformPoint,
} from './assembly'

function part(key: string, role: WorkbenchPart['role'] = 'printable', occurrences: WorkbenchOccurrence[] = []): WorkbenchPart {
  return {
    uuid: `${key}-uuid`,
    key,
    aliases: [],
    role,
    status: role === 'reference' ? 'reference' : 'active',
    artifactState: 'indexed',
    geometryAuthority: 'step',
    qualityLabel: 'Exact',
    occurrenceCount: occurrences.length,
    occurrenceIds: occurrences.map((occurrence) => occurrence.id),
    occurrences,
    authorityHash: `${key}-step`,
    displayArtifact: { contentHash: `${key}-stl`, format: 'stl', url: `/models/${key}`, revision: 3 },
    bounds: null,
    warnings: [],
  }
}

const occurrence = (id: string, translationMm: [number, number, number] = [0, 0, 0]): WorkbenchOccurrence => ({
  assemblyId: 'active', id, translationMm, rotationDeg: [0, 0, 0],
})

describe('progressive active assembly planning', () => {
  it('loads the selected part first, shares one fetch across repetitions, and includes the complete assembly', () => {
    const selected = part('selected', 'printable', [occurrence('selected-left'), occurrence('selected-right')])
    const other = part('other', 'printable', [occurrence('other-main')])
    const reference = part('reference', 'reference', [occurrence('reference-main')])

    const plan = planAssemblyLoads([other, reference, selected], 'active', selected.uuid)

    expect(plan.map((item) => item.part.key)).toEqual(['selected', 'other', 'reference'])
    expect(plan[0].occurrences.map((item) => item.id)).toEqual(['selected-left', 'selected-right'])
    expect(planAssemblyLoads([other, reference, selected], 'active', reference.uuid)[0].part.key).toBe('reference')
  })

  it('never schedules beyond the configured concurrency budget', () => {
    const plan = Array.from({ length: 8 }, (_, index) => part(`part-${index}`, 'printable', [occurrence(`occ-${index}`)]))
      .flatMap((item) => planAssemblyLoads([item], 'active', null))
    const records = reconcileLoadRecords({}, plan)
    const first = nextAssemblyLoadBatch(plan, records, 3)
    expect(first).toHaveLength(3)
    first.forEach((item) => { records[item.key] = { ...records[item.key], state: 'loading' } })
    expect(nextAssemblyLoadBatch(plan, records, 3)).toEqual([])
    records[first[0].key] = { ...records[first[0].key], state: 'visible' }
    expect(nextAssemblyLoadBatch(plan, records, 3)).toHaveLength(1)
  })

  it('keeps multiple explicitly selected reference parts visible together', () => {
    const lid = part('lid', 'reference', [occurrence('lid-main')])
    const axleWheel = part('axle-wheel', 'reference', [occurrence('axle-wheel-main')])
    const body = part('body', 'printable', [occurrence('body-main')])

    const plan = planAssemblyLoads([body, lid, axleWheel], 'active', axleWheel.uuid, [lid.uuid, axleWheel.uuid])

    expect(plan.map((item) => item.part.key)).toEqual(['axle-wheel', 'lid'])
  })

  it('applies the same XYZ rotation and translation contract used by occurrence meshes', () => {
    const placement = {
      assemblyId: 'active',
      id: 'rotated',
      translationMm: [10, 20, 30],
      rotationDeg: [0, 0, 90],
    } satisfies WorkbenchOccurrence
    const transformed = transformPoint([2, 0, 0], placement)
    expect(transformed[0]).toBeCloseTo(10)
    expect(transformed[1]).toBeCloseTo(22)
    expect(transformed[2]).toBeCloseTo(30)
    expect(transformExactFeature({
      id: 'edge-1',
      kind: 'line_edge',
      quality: 'exact',
      source: 'step_topology',
      startMm: [0, 0, 0],
      endMm: [2, 0, 0],
      midpointMm: [1, 0, 0],
      lengthMm: 2,
    }, placement)).toMatchObject({
      startMm: [10, 20, 30],
      lengthMm: 2,
    })
  })
})

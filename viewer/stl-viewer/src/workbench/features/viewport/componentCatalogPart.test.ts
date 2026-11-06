import { expect, it } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { componentCatalogPart, type SceneComponent } from './componentInspection'

const part = (uuid: string, key: string, aliases: string[] = []): WorkbenchPart => ({
  uuid, key, aliases, category: 'make', role: 'printable', status: 'active',
  artifactState: 'indexed', geometryAuthority: 'step', qualityLabel: 'Exact',
  occurrenceCount: 0, occurrenceIds: [], occurrences: [], authorityHash: null,
  displayArtifact: null, bounds: null, warnings: [],
})
const component: SceneComponent = { key: 'mesh', modelKey: 'view:rev', partUuid: 'view',
  occurrenceId: 'robot', label: 'front bracket 2', context: 'Robot',
  bounds: { min: [0, 0, 0], max: [1, 1, 1] } }
const bracket = part('bracket', 'shelf_bracket', ['front_bracket_2'])

it('links a view occurrence through its explicit project alias despite STEP label spacing', () => {
  expect(componentCatalogPart(component, [bracket])).toBe(bracket)
})
it('links exact keys without guessing from prefixes or display names', () => {
  expect(componentCatalogPart({ ...component, label: 'shelf_bracket' }, [bracket])).toBe(bracket)
  expect(componentCatalogPart({ ...component, label: 'shelf_bracket_3' }, [bracket])).toBeNull()
  expect(componentCatalogPart(component, [{ ...bracket, aliases: [], displayName: component.label }])).toBeNull()
})
it('keeps embedded UUID links authoritative, including unresolved links', () => {
  const other = part('other', 'other_part')
  expect(componentCatalogPart({ ...component, linkedPartUuid: 'other' }, [bracket, other])).toBe(other)
  expect(componentCatalogPart({ ...component, linkedPartUuid: 'deleted' }, [bracket])).toBeNull()
})
it('keeps individually loaded catalog parts linked to their owner', () => {
  expect(componentCatalogPart({ ...component, partUuid: 'bracket' }, [bracket])).toBe(bracket)
})
it('links a single-part study to its own files while leaving assembly components individually identified', () => {
  const study = { ...part('view', 'study'), category: 'view' as const }
  expect(componentCatalogPart({ ...component, modelComponentCount: 1 }, [study])).toBe(study)
  expect(componentCatalogPart({ ...component, modelComponentCount: 2 }, [study])).toBeNull()
  expect(componentCatalogPart({ ...component, linkedPartUuid: 'view' }, [study])).toBe(study)
})
it('resolves repeated display labels through the original source label and declared occurrence identity', () => {
  const placed = { ...bracket, aliases: [], occurrenceIds: ['left_support'] }
  expect(componentCatalogPart({ ...component, label: 'left support (2)', sourceLabel: 'left_support' }, [placed])).toBe(placed)
})
it('rejects ambiguous aliases and excludes the view record itself', () => {
  expect(componentCatalogPart(component, [bracket, part('other', 'other', ['front bracket 2'])])).toBeNull()
  const view = { ...part('view', 'robot', ['front bracket 2']), category: 'view' as const }
  expect(componentCatalogPart(component, [view, bracket])).toBe(bracket)
  expect(componentCatalogPart(component, [view])).toBeNull()
  expect(componentCatalogPart(null, [bracket])).toBeNull()
})

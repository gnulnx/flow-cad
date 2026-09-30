import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { expect, it, vi } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { createTestWorkbenchClient } from '../../testClient'
import { WorkbenchViewport } from './WorkbenchViewport'
import type ModelCanvas from './ModelCanvas'
import type { ComponentProps } from 'react'

const fixture = vi.hoisted(() => ({
  components: ['Cover', 'Motor'].map((label, index) => ({
    key: `mesh-${index}`, modelKey: 'view:rev', partUuid: 'view', occurrenceId: 'view-installed', label,
    context: 'Robot view', bounds: { min: [0, 0, 0] as [number, number, number], max: [10, 10, 10] as [number, number, number] },
  })),
  queue: {} as Record<string, unknown>,
  canvas: null as ComponentProps<typeof ModelCanvas> | null,
}))

vi.mock('./useAssemblyDisplayQueue', () => ({ useAssemblyDisplayQueue: () => fixture.queue }))
vi.mock('./ModelCanvas', () => ({ default: function Canvas(props: ComponentProps<typeof ModelCanvas>) {
  fixture.canvas = props
  useEffect(() => props.onComponentsChange(fixture.components), [props.onComponentsChange])
  return <div>{fixture.components.filter((component) => !props.hiddenComponentKeys.has(component.key)).map((component) => (
    <button key={component.key} onClick={() => { props.onSelectPart?.(component.partUuid); props.onComponentSelected(component.key) }}
      onContextMenu={(event) => { event.preventDefault(); props.onComponentContextMenu?.({ key: component.key, clientX: 200, clientY: 200 }) }}>Geometry {component.label}</button>
  ))}</div>
} }))

it('connects mesh clicks, peel mode, hidden list recovery and shortcuts without changing loads or camera', async () => {
  const part: WorkbenchPart = {
    uuid: 'view', key: 'robot_closed', displayName: 'Closed robot', aliases: [], role: 'inspection', status: 'active',
    artifactState: 'visible', geometryAuthority: 'step', qualityLabel: 'Exact', occurrenceCount: 1,
    occurrenceIds: ['view-installed'], occurrences: [{ id: 'view-installed', assemblyId: 'active', translationMm: [0, 0, 0], rotationDeg: [0, 0, 0] }],
    authorityHash: 'step-rev', displayArtifact: { contentHash: 'rev', format: 'glb', url: '/display', revision: 1 }, bounds: null, warnings: [],
  }
  const models = [{ key: 'view:rev', part, occurrences: part.occurrences, artifactBytes: new ArrayBuffer(0) }]
  fixture.queue = { models, partStates: { view: 'visible' }, visibleOccurrenceIds: ['view-installed'], artifactHashes: { view: 'rev' },
    progress: { total: 1, visible: 1, queued: 0, loading: 0, failed: 0 }, selectedOccurrence: part.occurrences[0], reportVisible: vi.fn(), reportParseFailure: vi.fn() }
  const user = userEvent.setup()
  const client = createTestWorkbenchClient()
  const onSelectPart = vi.fn()
  const onAssemblyStateChange = vi.fn()
  render(<WorkbenchViewport client={client} parts={[part]} part={part} visiblePartUuids={['view']}
    backendRevision={1} onSelectPart={onSelectPart} onAssemblyStateChange={onAssemblyStateChange} />)
  await screen.findByRole('button', { name: 'Geometry Cover' })
  fireEvent.contextMenu(screen.getByRole('button', { name: 'Geometry Cover' }))
  expect(screen.getByRole('menu', { name: 'Part actions' })).toBeVisible()
  await user.click(screen.getByRole('menuitem', { name: /Hide part/ }))
  expect(screen.queryByRole('button', { name: 'Geometry Cover' })).not.toBeInTheDocument()
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Undo' }))
  expect(screen.getByRole('button', { name: 'Geometry Cover' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Click to hide' }))
  await user.click(screen.getByRole('button', { name: 'Geometry Cover' }))
  expect(screen.queryByRole('button', { name: 'Geometry Cover' })).not.toBeInTheDocument()
  expect(onSelectPart).toHaveBeenCalledWith('view')
  expect(fixture.canvas?.models).toBe(models)
  expect(fixture.canvas?.fitRequest).toBe(0)
  await user.click(screen.getByRole('button', { name: 'Geometry Motor' }))
  expect(screen.getByRole('button', { name: '2 hidden' })).toBeVisible()
  expect(onAssemblyStateChange).toHaveBeenLastCalledWith(expect.objectContaining({ visibleOccurrenceIds: [] }))
  await user.keyboard('{Escape}')
  expect(screen.getByRole('button', { name: 'Click to hide' })).toHaveAttribute('aria-pressed', 'false')
  await user.click(screen.getByRole('button', { name: '2 hidden' }))
  await user.click(screen.getByRole('button', { name: 'Show Motor' }))
  await user.click(screen.getByRole('button', { name: 'Geometry Motor' }))
  await user.keyboard('H')
  expect(screen.getByRole('button', { name: 'Geometry Cover' })).toBeVisible()
  await user.keyboard('h')
  expect(screen.queryByRole('button', { name: 'Geometry Motor' })).not.toBeInTheDocument()
  await user.type(screen.getByRole('searchbox'), 'h')
  expect(screen.getByRole('button', { name: '1 hidden' })).toBeVisible()
  await user.clear(screen.getByRole('searchbox'))
  await user.click(screen.getByRole('button', { name: 'Close parts in view' }))
  await user.click(screen.getByRole('button', { name: 'Measure geometry' }))
  expect(screen.getByText('Exit Measure and use Show all to restore exact snapping for this view.')).toBeVisible()
  await user.keyboard('H')
  expect(screen.getByRole('button', { name: '1 hidden' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Show all' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Measure geometry' }))
  await user.click(screen.getByRole('button', { name: 'Show all' }))
  await waitFor(() => expect(onAssemblyStateChange).toHaveBeenLastCalledWith(expect.objectContaining({ visibleOccurrenceIds: ['view-installed'] })))
  expect(fixture.canvas?.models).toBe(models)
  expect(fixture.canvas?.fitRequest).toBe(0)
})

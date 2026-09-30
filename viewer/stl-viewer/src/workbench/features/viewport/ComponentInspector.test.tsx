import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, it, vi } from 'vitest'
import { ComponentInspector } from './ComponentInspector'
import type { SceneComponent } from './componentInspection'
import { useComponentInspection } from './useComponentInspection'

const components: SceneComponent[] = ['Outer cover', 'Drive motor', 'Support'].map((label, index) => ({
  key: `component-${index}`, modelKey: 'view-v1', partUuid: 'view', occurrenceId: 'installed', label,
  context: 'Actuator assembly', bounds: { min: [0, 0, 0], max: [1, 1, 1] },
}))

function Fixture() {
  const inspection = useComponentInspection(components, 'view-v1')
  const [peel, setPeel] = useState(false)
  return <ComponentInspector components={components} inspection={inspection} peel={peel} disabled={false}
    onPeel={setPeel} onSelect={(component) => inspection.select(component.key)} onFrame={vi.fn()} />
}

it('lets users find hidden parts, restore one, isolate a selection and undo without losing earlier hides', async () => {
  const user = userEvent.setup()
  render(<Fixture />)
  await user.click(screen.getByRole('button', { name: 'Parts in view (3)' }))
  const panel = screen.getByRole('complementary', { name: 'Parts in loaded view' })
  await user.click(within(panel).getByRole('button', { name: 'Hide Outer cover' }))
  await user.click(within(panel).getByRole('button', { name: 'Select Drive motor' }))
  await user.click(screen.getByRole('button', { name: 'Isolate' }))
  expect(screen.getByRole('button', { name: '2 hidden' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Undo' }))
  expect(screen.getByRole('button', { name: '1 hidden' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: '1 hidden' }))
  expect(within(panel).queryByRole('button', { name: 'Hide Drive motor' })).not.toBeInTheDocument()
  await user.type(screen.getByRole('searchbox'), 'cover')
  await user.click(screen.getByRole('button', { name: 'Show Outer cover' }))
  expect(screen.getByText('No hidden parts.')).toBeVisible()
  expect(screen.getByRole('button', { name: '0 hidden' })).toBeVisible()
})

it('keeps recovery controls available with all parts hidden', async () => {
  const user = userEvent.setup()
  render(<Fixture />)
  await user.click(screen.getByRole('button', { name: 'Parts in view (3)' }))
  for (const component of components) await user.click(screen.getByRole('button', { name: `Hide ${component.label}` }))
  expect(screen.getByRole('status')).toHaveTextContent('Everything is hidden')
  await user.click(screen.getByRole('button', { name: 'Show all' }))
  expect(screen.getByRole('button', { name: '0 hidden' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Click to hide' }))
  expect(screen.getByRole('status')).toHaveTextContent('Click a part to hide it')
})

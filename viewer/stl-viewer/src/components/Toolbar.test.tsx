import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Toolbar from './Toolbar'

describe('Toolbar measurement controls', () => {
  it('toggles the Tape Tool and clears measurements', async () => {
    const user = userEvent.setup()
    const onTapeModeChange = vi.fn()
    const onClearMeasurements = vi.fn()

    render(
      <Toolbar
        onFitToView={vi.fn()}
        onFrameSelected={vi.fn()}
        onReload={vi.fn()}
        statusMessage="ready"
        rotationMode="turntable"
        onRotationModeChange={vi.fn()}
        tapeMode={false}
        onTapeModeChange={onTapeModeChange}
        onClearMeasurements={onClearMeasurements}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Tape' }))
    await user.click(screen.getByRole('button', { name: 'Clear Measurements' }))

    expect(onTapeModeChange).toHaveBeenCalledWith(true)
    expect(onClearMeasurements).toHaveBeenCalledTimes(1)
  })
})

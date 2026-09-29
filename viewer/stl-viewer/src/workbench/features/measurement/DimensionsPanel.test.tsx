import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DimensionsPanel, boundsDimensions } from './DimensionsPanel'

describe('display dimensions', () => {
  it('uses extents instead of coordinates and labels unfinished display bounds', async () => {
    const bounds = { min: [-121, 65, -50], max: [-55, 115, -44] } as const
    const mutable = { min: [...bounds.min] as [number, number, number], max: [...bounds.max] as [number, number, number] }
    expect(boundsDimensions(mutable)).toEqual([66, 50, 6])
    const onScope = vi.fn()
    render(<DimensionsPanel bounds={mutable} scope="selected" onScope={onScope} loading />)
    expect(screen.getByText('66.00 mm')).toBeInTheDocument()
    expect(screen.getByText('50.00 mm')).toBeInTheDocument()
    expect(screen.getByText('6.00 mm')).toBeInTheDocument()
    expect(screen.getByText(/incomplete/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Dimension scope'), 'visible')
    expect(onScope).toHaveBeenCalledWith('visible')
  })
})

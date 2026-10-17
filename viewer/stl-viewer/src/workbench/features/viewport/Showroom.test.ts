import { describe, expect, it } from 'vitest'
import { showroomLayout } from './Showroom'

describe('showroom placement', () => {
  it('follows installed bounds away from the origin and puts the floor below every component', () => {
    const layout = showroomLayout({ min: [1000, -800, -50], max: [1400, -600, 550] })
    expect(layout.center).toEqual([1200, -700, 250])
    expect(layout.size).toBe(600)
    expect(layout.floor).toBeLessThan(-50)
  })
  it('supports empty and zero-size scenes without a singular shadow camera', () => {
    expect(showroomLayout(null).size).toBeGreaterThan(0)
    expect(showroomLayout({ min: [0, 0, 0], max: [0, 0, 0] }).size).toBeGreaterThan(0)
  })
})

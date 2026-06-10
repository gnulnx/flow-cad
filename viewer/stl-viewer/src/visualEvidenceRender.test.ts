import { describe, expect, it } from 'vitest'
import { cameraDirectionForVisualEvidenceView, renderVisualEvidenceCapture } from './visualEvidenceRender'

describe('visual evidence rendering helpers', () => {
  it('maps named evidence views to deterministic camera directions', () => {
    expect(cameraDirectionForVisualEvidenceView('front').toArray()).toEqual([0, 1, 0])
    expect(cameraDirectionForVisualEvidenceView('back').toArray()).toEqual([0, -1, 0])
    expect(cameraDirectionForVisualEvidenceView('left').toArray()).toEqual([-1, 0, 0])
    expect(cameraDirectionForVisualEvidenceView('right').toArray()).toEqual([1, 0, 0])
    expect(cameraDirectionForVisualEvidenceView('top').toArray()).toEqual([0, 0, 1])
    expect(cameraDirectionForVisualEvidenceView('bottom').toArray()).toEqual([0, 0, -1])

    const iso = cameraDirectionForVisualEvidenceView('iso')
    expect(iso.length()).toBeCloseTo(1)
    expect(iso.x).toBeGreaterThan(0)
    expect(iso.y).toBeGreaterThan(0)
    expect(iso.z).toBeGreaterThan(0)
  })

  it('rejects capture requests without visible models before creating WebGL state', async () => {
    await expect(renderVisualEvidenceCapture({ models: [], view: 'iso' })).rejects.toThrow(
      'No visible models available for visual evidence render',
    )
  })
})

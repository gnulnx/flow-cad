import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AnnotationOverlay } from './AnnotationOverlay'
import { buildAnnotationSvgDataUrl } from './capture'

describe('annotation screenshot composition', () => {
  it('serializes the actual viewport SVG overlay with screenshot metadata', () => {
    render(<AnnotationOverlay initialMarks={[{
      id: 'review-arrow',
      kind: 'arrow',
      points: [[0.1, 0.2], [0.8, 0.7]],
      color: '#79cbd1',
      strokeWidth: 2,
      intent: 'review_intent',
    }]} />)
    const overlay = screen.getByLabelText('Viewport annotations') as unknown as SVGSVGElement
    const dataUrl = buildAnnotationSvgDataUrl(overlay, 1280, 720)
    const decoded = decodeURIComponent(dataUrl.split(',', 2)[1])
    expect(dataUrl).toMatch(/^data:image\/svg\+xml;charset=utf-8,/)
    expect(decoded).toContain('width="1280"')
    expect(decoded).toContain('height="720"')
    expect(decoded).toContain('data-render-context="viewport-canvas"')
    expect(decoded).toContain('data-review-intent="true"')
    expect(decoded).toContain('data-mark-id="review-arrow"')
  })
})

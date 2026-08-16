import { useMemo, useState, type PointerEvent as ReactPointerEvent } from 'react'
import type { ThreadViewportAnnotation, ViewportMarkupTool } from '../types'

interface ViewportMarkupOverlayProps {
  active: boolean
  tool: ViewportMarkupTool
  noteText: string
  annotations: ThreadViewportAnnotation[]
  onChange: (annotations: ThreadViewportAnnotation[]) => void
}

interface MarkupPoint {
  x: number
  y: number
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value))
}

function pointFromEvent(event: ReactPointerEvent<SVGSVGElement>): MarkupPoint {
  const bounds = event.currentTarget.getBoundingClientRect()
  const width = bounds.width || event.currentTarget.clientWidth || 1
  const height = bounds.height || event.currentTarget.clientHeight || 1
  return {
    x: clamp01((event.clientX - bounds.left) / width),
    y: clamp01((event.clientY - bounds.top) / height),
  }
}

function pointDistance(a: MarkupPoint, b: MarkupPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function pathFromPoints(points: MarkupPoint[]) {
  if (!points.length) return ''
  const [first, ...rest] = points
  return [
    `M ${first.x} ${first.y}`,
    ...rest.map((point) => `L ${point.x} ${point.y}`),
  ].join(' ')
}

export default function ViewportMarkupOverlay({
  active,
  tool,
  noteText,
  annotations,
  onChange,
}: ViewportMarkupOverlayProps) {
  const [draftPoints, setDraftPoints] = useState<MarkupPoint[]>([])
  const [draftCircle, setDraftCircle] = useState<{ start: MarkupPoint; current: MarkupPoint } | null>(null)

  const draftAnnotation = useMemo(() => {
    if (tool === 'pen' && draftPoints.length > 1) {
      return {
        kind: 'freehand' as const,
        points: draftPoints,
        color: '#f97316',
        width: 0.006,
      }
    }
    if (tool === 'circle' && draftCircle) {
      return {
        kind: 'circle' as const,
        x: draftCircle.start.x,
        y: draftCircle.start.y,
        radius: pointDistance(draftCircle.start, draftCircle.current),
      }
    }
    return null
  }, [draftCircle, draftPoints, tool])

  const commitDraft = () => {
    if (draftAnnotation) {
      onChange([...annotations, draftAnnotation])
    }
    setDraftPoints([])
    setDraftCircle(null)
  }

  const handlePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!active) return
    event.preventDefault()
    event.currentTarget.setPointerCapture?.(event.pointerId)
    const point = pointFromEvent(event)
    if (tool === 'note') {
      const text = noteText.trim()
      if (text) {
        onChange([...annotations, { kind: 'note', text, x: point.x, y: point.y }])
      }
      return
    }
    if (tool === 'circle') {
      setDraftCircle({ start: point, current: point })
      return
    }
    setDraftPoints([point])
  }

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!active) return
    const point = pointFromEvent(event)
    if (tool === 'circle' && draftCircle) {
      setDraftCircle({ ...draftCircle, current: point })
      return
    }
    if (tool === 'pen' && draftPoints.length) {
      const lastPoint = draftPoints[draftPoints.length - 1]
      if (pointDistance(lastPoint, point) > 0.004) {
        setDraftPoints((current) => [...current, point])
      }
    }
  }

  const handlePointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!active) return
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    commitDraft()
  }

  const renderAnnotation = (annotation: ThreadViewportAnnotation, index: number) => {
    if (annotation.kind === 'freehand') {
      return (
        <path
          key={`freehand-${index}`}
          d={pathFromPoints(annotation.points)}
          className="viewport-markup-freehand"
          vectorEffect="non-scaling-stroke"
        />
      )
    }
    if (annotation.kind === 'circle') {
      return (
        <circle
          key={`circle-${index}`}
          cx={annotation.x}
          cy={annotation.y}
          r={annotation.radius}
          className="viewport-markup-circle"
          vectorEffect="non-scaling-stroke"
        />
      )
    }
    return (
      <g key={`note-${index}`} className="viewport-markup-note">
        <circle cx={annotation.x} cy={annotation.y} r="0.012" vectorEffect="non-scaling-stroke" />
        <text x={annotation.x + 0.018} y={annotation.y - 0.018} fontSize="0.035">{annotation.text}</text>
      </g>
    )
  }

  return (
    <div className={`viewport-markup-layer ${active ? 'active' : ''}`} aria-hidden={!active && !annotations.length}>
      <svg
        className="viewport-markup-surface"
        aria-label="Viewport markup surface"
        role="img"
        viewBox="0 0 1 1"
        preserveAspectRatio="none"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => {
          setDraftPoints([])
          setDraftCircle(null)
        }}
      >
        {annotations.map(renderAnnotation)}
        {draftAnnotation ? renderAnnotation(draftAnnotation, -1) : null}
      </svg>
      {active ? (
        <div className="viewport-markup-hint">
          {tool === 'note' ? 'Click to place text' : tool === 'circle' ? 'Drag to circle an area' : 'Draw over the view'}
        </div>
      ) : null}
    </div>
  )
}

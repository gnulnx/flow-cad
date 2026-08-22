import {
  useEffect,
  useId,
  useReducer,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from 'react'
import type { AnnotationMark, AnnotationTool } from './contracts'
import { annotationReducer, ANNOTATION_COLORS, createAnnotationState, normalizePointer } from './state'
import './annotation.css'

interface AnnotationOverlayProps {
  initialMarks?: AnnotationMark[]
  overlayRef?: RefObject<SVGSVGElement>
  onActiveChange?(active: boolean): void
  onChange?(marks: AnnotationMark[], hidden: boolean): void
  onSave?(marks: AnnotationMark[], hidden: boolean): void | Promise<void>
  onAskAgent?(marks: AnnotationMark[]): void
}

const TOOLS: readonly [AnnotationTool, string][] = [
  ['pen', 'Pen'],
  ['circle', 'Circle'],
  ['arrow', 'Arrow'],
  ['text', 'Text'],
]

let markSequence = 0

export function AnnotationOverlay({
  initialMarks = [],
  overlayRef,
  onActiveChange,
  onChange,
  onSave,
  onAskAgent,
}: AnnotationOverlayProps) {
  const [state, dispatch] = useReducer(annotationReducer, initialMarks, createAnnotationState)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle')
  const markerId = `annotation-arrow-${useId().replace(/[^A-Za-z0-9_-]/g, '')}`
  const renderedMarks = state.draft ? [...state.marks, state.draft] : state.marks

  useEffect(() => {
    onChange?.(state.marks, !state.visible)
  }, [onChange, state.marks, state.visible])

  useEffect(() => {
    if (!state.active) return
    const exit = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      dispatch({ type: 'escape' })
      onActiveChange?.(false)
    }
    window.addEventListener('keydown', exit)
    return () => window.removeEventListener('keydown', exit)
  }, [onActiveChange, state.active])

  const toggleActive = () => {
    dispatch({ type: 'toggle_active' })
    onActiveChange?.(!state.active)
  }

  const point = (event: ReactPointerEvent<SVGSVGElement>) => normalizePointer(
    event.clientX,
    event.clientY,
    event.currentTarget.getBoundingClientRect(),
  )

  const begin = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!state.active || !state.visible || event.button !== 0) return
    event.preventDefault()
    event.stopPropagation()
    event.currentTarget.setPointerCapture?.(event.pointerId)
    dispatch({ type: 'start', id: nextMarkId(state.tool), point: point(event) })
  }

  const move = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!state.active || !state.visible || !state.draft) return
    event.preventDefault()
    event.stopPropagation()
    dispatch({ type: 'move', point: point(event) })
  }

  const finish = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!state.active || !state.visible || !state.draft) return
    event.preventDefault()
    event.stopPropagation()
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    dispatch({ type: 'finish', point: point(event) })
  }

  const save = async () => {
    if (!onSave || saveState === 'saving') return
    setSaveState('saving')
    try {
      await onSave(state.marks, !state.visible)
      setSaveState('saved')
    } catch {
      setSaveState('failed')
    }
  }

  return (
    <div className="annotation-overlay" data-active={state.active} data-visible={state.visible}>
      <div className="annotation-edge-controls" onPointerDown={(event) => event.stopPropagation()}>
        <button
          type="button"
          className="annotation-toggle"
          aria-pressed={state.active}
          onClick={toggleActive}
        >
          Annotate
          {state.marks.length ? <span aria-label={`${state.marks.length} marks`}>{state.marks.length}</span> : null}
        </button>
        {state.active ? (
          <div className="annotation-palette" role="toolbar" aria-label="Annotation tools">
            <div className="annotation-palette__tools">
              {TOOLS.map(([tool, label]) => (
                <button
                  type="button"
                  key={tool}
                  aria-label={label}
                  aria-pressed={state.tool === tool}
                  onClick={() => dispatch({ type: 'set_tool', tool })}
                >
                  {toolGlyph(tool)}
                </button>
              ))}
            </div>
            <div className="annotation-palette__colors" aria-label="Annotation color">
              {ANNOTATION_COLORS.map((color) => (
                <button
                  type="button"
                  key={color}
                  aria-label={`Use color ${color}`}
                  aria-pressed={state.color === color}
                  style={{ '--annotation-swatch': color } as CSSProperties}
                  onClick={() => dispatch({ type: 'set_color', color })}
                />
              ))}
            </div>
            {state.tool === 'text' ? (
              <input
                aria-label="Annotation text"
                value={state.text}
                maxLength={4000}
                placeholder="Type note, then click"
                onChange={(event) => dispatch({ type: 'set_text', text: event.target.value })}
              />
            ) : null}
            <div className="annotation-palette__actions">
              <button type="button" onClick={() => dispatch({ type: 'undo' })} disabled={!state.draft && state.marks.length === 0}>Undo</button>
              <button type="button" onClick={() => dispatch({ type: 'clear' })} disabled={state.marks.length === 0}>Clear</button>
              <button type="button" onClick={() => dispatch({ type: 'toggle_visible' })}>{state.visible ? 'Hide' : 'Show'}</button>
              {onSave ? <button type="button" onClick={() => void save()}>{saveState === 'saving' ? 'Saving…' : 'Save'}</button> : null}
              {onAskAgent ? (
                <button type="button" onClick={() => onAskAgent(state.marks)} disabled={state.marks.length === 0}>
                  Ask agent about this markup
                </button>
              ) : null}
            </div>
            {saveState === 'failed' ? <span className="annotation-save-state" role="alert">Save failed</span> : null}
            <span className="annotation-palette__hint">Esc exits</span>
          </div>
        ) : null}
      </div>
      <svg
        ref={overlayRef}
        className="annotation-surface"
        viewBox="0 0 1000 1000"
        preserveAspectRatio="none"
        aria-label="Viewport annotations"
        aria-hidden={!state.visible}
        data-interactive={state.active && state.visible}
        data-render-context="viewport-canvas"
        data-review-intent="true"
        onPointerDown={begin}
        onPointerMove={move}
        onPointerUp={finish}
        onPointerCancel={() => dispatch({ type: 'cancel_draft' })}
      >
        <defs>
          <marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
          </marker>
        </defs>
        {state.visible ? renderedMarks.map((mark) => renderMark(mark, markerId)) : null}
      </svg>
    </div>
  )
}

function renderMark(mark: AnnotationMark, markerId: string) {
  const common = {
    stroke: mark.color,
    strokeWidth: mark.strokeWidth,
    vectorEffect: 'non-scaling-stroke' as const,
    'data-mark-id': mark.id,
    'data-mark-kind': mark.kind,
  }
  if (mark.kind === 'pen') {
    return <polyline key={mark.id} {...common} points={mark.points.map(svgPoint).join(' ')} fill="none" strokeLinecap="round" strokeLinejoin="round" />
  }
  if (mark.kind === 'circle') {
    const [start, end] = mark.points
    return (
      <ellipse
        key={mark.id}
        {...common}
        cx={(start[0] + end[0]) * 500}
        cy={(start[1] + end[1]) * 500}
        rx={Math.abs(end[0] - start[0]) * 500}
        ry={Math.abs(end[1] - start[1]) * 500}
        fill="none"
      />
    )
  }
  if (mark.kind === 'arrow') {
    return <line key={mark.id} {...common} x1={mark.points[0][0] * 1000} y1={mark.points[0][1] * 1000} x2={mark.points[1][0] * 1000} y2={mark.points[1][1] * 1000} markerEnd={`url(#${markerId})`} />
  }
  return (
    <text
      key={mark.id}
      x={mark.points[0][0] * 1000}
      y={mark.points[0][1] * 1000}
      fill={mark.color}
      stroke="#0b1015"
      strokeWidth={3}
      paintOrder="stroke"
      fontSize={28}
      fontWeight={650}
      vectorEffect="non-scaling-stroke"
      data-mark-id={mark.id}
      data-mark-kind={mark.kind}
    >
      {mark.text}
    </text>
  )
}

function svgPoint(point: readonly [number, number]) {
  return `${point[0] * 1000},${point[1] * 1000}`
}

function nextMarkId(tool: AnnotationTool) {
  markSequence += 1
  return `${tool}_${Date.now().toString(36)}_${markSequence.toString(36)}`
}

function toolGlyph(tool: AnnotationTool) {
  return { pen: '✎', circle: '○', arrow: '↗', text: 'T' }[tool]
}

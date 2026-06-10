import type { ViewportMarkupTool } from '../types'

interface AnnotationToolbarProps {
  active: boolean
  tool: ViewportMarkupTool
  noteText: string
  annotationCount: number
  onToolChange: (tool: ViewportMarkupTool) => void
  onNoteTextChange: (value: string) => void
  onUndo: () => void
  onClear: () => void
  onClose: () => void
}

export default function AnnotationToolbar({
  active,
  tool,
  noteText,
  annotationCount,
  onToolChange,
  onNoteTextChange,
  onUndo,
  onClear,
  onClose,
}: AnnotationToolbarProps) {
  if (!active) return null

  return (
    <div className="viewport-annotation-toolbar" role="toolbar" aria-label="Annotation toolbar">
      {(['pen', 'circle', 'note'] as const).map((item) => (
        <button
          key={item}
          type="button"
          role="button"
          className={`btn-tool ${tool === item ? 'active' : ''}`}
          onClick={() => onToolChange(item)}
          aria-label={item === 'pen' ? 'Pen' : item === 'circle' ? 'Circle' : 'Text'}
        >
          {item === 'pen' ? 'Pen' : item === 'circle' ? 'Circle' : 'Text'}
        </button>
      ))}
      <input
        type="text"
        className="annotation-toolbar-input"
        aria-label="Annotation text"
        placeholder="Text label"
        value={noteText}
        onChange={(event) => onNoteTextChange(event.target.value)}
      />
      <button
        type="button"
        className="btn-tool"
        onClick={onUndo}
        disabled={annotationCount === 0}
        aria-label="Undo"
      >
        Undo
      </button>
      <button
        type="button"
        className="btn-tool"
        onClick={onClear}
        disabled={annotationCount === 0}
        aria-label="Clear"
      >
        Clear
      </button>
      <span className="annotation-count" aria-live="polite">{annotationCount} markups</span>
      <button
        type="button"
        className="btn-tool annotation-toolbar-close"
        onClick={onClose}
        aria-label="Close annotation toolbar"
      >
        Close
      </button>
    </div>
  )
}

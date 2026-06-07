import { useEffect, useState } from 'react'
import type { EditEntity } from '../types'

interface EditEntityControlsProps {
  componentId: string
  entityId: string
  entity: EditEntity
  onPatch: (componentId: string, patch: Record<string, unknown>) => Promise<void>
}

const AXES = ['X', 'Y', 'Z'] as const

function vectorDraft(values: [number, number, number]) {
  return values.map((value) => String(Number(value.toFixed(4)))) as [string, string, string]
}

function parsedVector(values: [string, string, string]) {
  const parsed = values.map((value) => Number(value)) as [number, number, number]
  return parsed.every((value) => Number.isFinite(value)) ? parsed : null
}

function replaceVectorValue(values: [string, string, string], index: number, value: string): [string, string, string] {
  const next = [...values] as [string, string, string]
  next[index] = value
  return next
}

export default function EditEntityControls({
  componentId,
  entityId,
  entity,
  onPatch,
}: EditEntityControlsProps) {
  const [centerDraft, setCenterDraft] = useState(vectorDraft(entity.transform.translation_mm))
  const [sizeDraft, setSizeDraft] = useState(vectorDraft(entity.size_mm))
  const [saving, setSaving] = useState<'center' | 'size' | null>(null)

  useEffect(() => {
    setCenterDraft(vectorDraft(entity.transform.translation_mm))
    setSizeDraft(vectorDraft(entity.size_mm))
  }, [entity])

  const centerVector = parsedVector(centerDraft)
  const sizeVector = parsedVector(sizeDraft)
  const canApplyCenter = Boolean(centerVector) && !saving
  const canApplySize = Boolean(sizeVector && sizeVector.every((value) => value > 0)) && !saving

  const applyCenter = async () => {
    if (!centerVector) return
    setSaving('center')
    try {
      await onPatch(componentId, { translation_mm: centerVector })
    } finally {
      setSaving(null)
    }
  }

  const applySize = async () => {
    if (!sizeVector || sizeVector.some((value) => value <= 0)) return
    setSaving('size')
    try {
      await onPatch(componentId, { size_mm: sizeVector })
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="edit-controls-panel" aria-label={`${entityId} edit controls`}>
      <div className="edit-controls-heading">{entityId}</div>
      <div className="edit-controls-grid">
        <div className="edit-vector-group">
          <div className="edit-vector-label">Center mm</div>
          {AXES.map((axis, index) => (
            <label key={axis} className="edit-vector-field">
              <span>{axis}</span>
              <input
                type="number"
                step="0.1"
                aria-label={`${entityId} center ${axis}`}
                value={centerDraft[index]}
                onChange={(event) => setCenterDraft(replaceVectorValue(centerDraft, index, event.target.value))}
              />
            </label>
          ))}
          <button type="button" className="edit-apply-button" disabled={!canApplyCenter} onClick={applyCenter}>
            Apply Center
          </button>
        </div>
        <div className="edit-vector-group">
          <div className="edit-vector-label">Size mm</div>
          {AXES.map((axis, index) => (
            <label key={axis} className="edit-vector-field">
              <span>{axis}</span>
              <input
                type="number"
                min="0.001"
                step="0.1"
                aria-label={`${entityId} size ${axis}`}
                value={sizeDraft[index]}
                onChange={(event) => setSizeDraft(replaceVectorValue(sizeDraft, index, event.target.value))}
              />
            </label>
          ))}
          <button type="button" className="edit-apply-button" disabled={!canApplySize} onClick={applySize}>
            Apply Size
          </button>
        </div>
      </div>
    </div>
  )
}

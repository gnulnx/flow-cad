import { useEffect, useState } from 'react'
import type { EditEntity, EditPoint } from '../types'

interface EditEntityControlsProps {
  componentId: string
  entityId: string
  entity: EditEntity
  booleanToolOptions: Array<{ componentId: string; entityId: string; label: string }>
  points: Record<string, EditPoint>
  activePointId: string | null
  onActivePointChange: (pointId: string | null) => void
  onPatch: (componentId: string, patch: Record<string, unknown>) => Promise<void>
  onCreatePoint: (positionMm: [number, number, number]) => Promise<void>
  onPatchPoint: (pointId: string, patch: Record<string, unknown>) => Promise<void>
  onCreateHole: (
    componentId: string,
    pointId: string,
    preset: string,
    axis: [number, number, number],
  ) => Promise<void>
  onCreateBoolean: (operation: 'fuse' | 'cut', targetComponentId: string, toolComponentId: string) => Promise<void>
  onCreateSplit: (targetComponentId: string, axis: [number, number, number]) => Promise<void>
}

const AXES = ['X', 'Y', 'Z'] as const
const HOLE_PRESETS = [
  { id: 'm4_clearance', label: 'M4 clearance' },
  { id: 'm5_clearance', label: 'M5 clearance' },
]
const HOLE_AXES: Array<{ id: string; label: string; axis: [number, number, number] }> = [
  { id: 'x', label: 'X', axis: [1, 0, 0] },
  { id: 'y', label: 'Y', axis: [0, 1, 0] },
  { id: 'z', label: 'Z', axis: [0, 0, 1] },
]

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
  booleanToolOptions,
  points,
  activePointId,
  onActivePointChange,
  onPatch,
  onCreatePoint,
  onPatchPoint,
  onCreateHole,
  onCreateBoolean,
  onCreateSplit,
}: EditEntityControlsProps) {
  const [centerDraft, setCenterDraft] = useState(vectorDraft(entity.transform.translation_mm))
  const [sizeDraft, setSizeDraft] = useState(vectorDraft(entity.size_mm))
  const [newPointDraft, setNewPointDraft] = useState<[string, string, string]>(['0', '0', '0'])
  const [activePointDraft, setActivePointDraft] = useState<[string, string, string]>(['0', '0', '0'])
  const [holePreset, setHolePreset] = useState('m4_clearance')
  const [holeAxisId, setHoleAxisId] = useState('z')
  const [splitAxisId, setSplitAxisId] = useState('z')
  const [booleanToolComponentId, setBooleanToolComponentId] = useState('')
  const [saving, setSaving] = useState<'center' | 'size' | 'point' | 'activePoint' | 'hole' | 'boolean' | 'split' | null>(null)
  const pointEntries = Object.entries(points)
  const activePoint = activePointId ? points[activePointId] : null

  useEffect(() => {
    setCenterDraft(vectorDraft(entity.transform.translation_mm))
    setSizeDraft(vectorDraft(entity.size_mm))
  }, [entity])

  useEffect(() => {
    if (activePoint) {
      setActivePointDraft(vectorDraft(activePoint.position_mm))
    }
  }, [activePoint])

  useEffect(() => {
    setBooleanToolComponentId((current) => {
      if (current && booleanToolOptions.some((option) => option.componentId === current)) return current
      return booleanToolOptions[0]?.componentId ?? ''
    })
  }, [booleanToolOptions])

  const centerVector = parsedVector(centerDraft)
  const sizeVector = parsedVector(sizeDraft)
  const newPointVector = parsedVector(newPointDraft)
  const activePointVector = parsedVector(activePointDraft)
  const canApplyCenter = Boolean(centerVector) && !saving
  const canApplySize = Boolean(sizeVector && sizeVector.every((value) => value > 0)) && !saving
  const canCreatePoint = Boolean(newPointVector) && !saving
  const canApplyActivePoint = Boolean(activePoint && activePointVector) && !saving
  const canCutHole = Boolean(activePoint && activePoint.quality === 'exact') && !saving
  const canApplyBoolean = Boolean(booleanToolComponentId) && !saving

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

  const createPoint = async () => {
    if (!newPointVector) return
    setSaving('point')
    try {
      await onCreatePoint(newPointVector)
    } finally {
      setSaving(null)
    }
  }

  const applyActivePoint = async () => {
    if (!activePointId || !activePointVector) return
    setSaving('activePoint')
    try {
      await onPatchPoint(activePointId, {
        position_mm: activePointVector,
        quality: activePoint?.quality ?? 'exact',
        source: activePoint?.source ?? { kind: 'typed_coordinates' },
      })
    } finally {
      setSaving(null)
    }
  }

  const cutHole = async () => {
    if (!activePointId) return
    const axis = HOLE_AXES.find((candidate) => candidate.id === holeAxisId)?.axis ?? [0, 0, 1]
    setSaving('hole')
    try {
      await onCreateHole(componentId, activePointId, holePreset, axis)
    } finally {
      setSaving(null)
    }
  }

  const applyBoolean = (operation: 'fuse' | 'cut') => async () => {
    if (!booleanToolComponentId) return
    setSaving('boolean')
    try {
      await onCreateBoolean(operation, componentId, booleanToolComponentId)
    } finally {
      setSaving(null)
    }
  }

  const splitBody = async () => {
    const axis = HOLE_AXES.find((candidate) => candidate.id === splitAxisId)?.axis ?? [0, 0, 1]
    setSaving('split')
    try {
      await onCreateSplit(componentId, axis)
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
      <div className="edit-controls-section">
        <div className="edit-vector-label">Point mm</div>
        <div className="edit-vector-group">
          {AXES.map((axis, index) => (
            <label key={axis} className="edit-vector-field">
              <span>{axis}</span>
              <input
                type="number"
                step="0.1"
                aria-label={`new point ${axis}`}
                value={newPointDraft[index]}
                onChange={(event) => setNewPointDraft(replaceVectorValue(newPointDraft, index, event.target.value))}
              />
            </label>
          ))}
          <button type="button" className="edit-apply-button" disabled={!canCreatePoint} onClick={createPoint}>
            Add Point
          </button>
        </div>
      </div>
      {pointEntries.length ? (
        <div className="edit-controls-section">
          <label className="edit-select-field">
            <span>Point</span>
            <select
              aria-label="Active edit point"
              value={activePointId ?? ''}
              onChange={(event) => onActivePointChange(event.target.value || null)}
            >
              <option value="">None</option>
              {pointEntries.map(([pointId, point]) => (
                <option key={pointId} value={pointId}>
                  {pointId} ({point.quality})
                </option>
              ))}
            </select>
          </label>
          {activePoint ? (
            <div className="edit-vector-group">
              {AXES.map((axis, index) => (
                <label key={axis} className="edit-vector-field">
                  <span>{axis}</span>
                  <input
                    type="number"
                    step="0.1"
                    aria-label={`${activePointId} point ${axis}`}
                    value={activePointDraft[index]}
                    onChange={(event) => setActivePointDraft(replaceVectorValue(activePointDraft, index, event.target.value))}
                  />
                </label>
              ))}
              <button type="button" className="edit-apply-button" disabled={!canApplyActivePoint} onClick={applyActivePoint}>
                Apply Point
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="edit-controls-section">
        <div className="edit-hole-row">
          <label className="edit-select-field">
            <span>Hole</span>
            <select
              aria-label={`${entityId} hole preset`}
              value={holePreset}
              onChange={(event) => setHolePreset(event.target.value)}
            >
              {HOLE_PRESETS.map((preset) => (
                <option key={preset.id} value={preset.id}>{preset.label}</option>
              ))}
            </select>
          </label>
          <label className="edit-select-field">
            <span>Axis</span>
            <select
              aria-label={`${entityId} hole axis`}
              value={holeAxisId}
              onChange={(event) => setHoleAxisId(event.target.value)}
            >
              {HOLE_AXES.map((axis) => (
                <option key={axis.id} value={axis.id}>{axis.label}</option>
              ))}
            </select>
          </label>
        </div>
        <button type="button" className="edit-apply-button" disabled={!canCutHole} onClick={cutHole}>
          Cut Through Hole
        </button>
      </div>
      <div className="edit-controls-section">
        <label className="edit-select-field">
          <span>Tool Body</span>
          <select
            aria-label={`${entityId} boolean tool`}
            value={booleanToolComponentId}
            disabled={!booleanToolOptions.length}
            onChange={(event) => setBooleanToolComponentId(event.target.value)}
          >
            {booleanToolOptions.length ? null : <option value="">None</option>}
            {booleanToolOptions.map((option) => (
              <option key={option.componentId} value={option.componentId}>{option.label}</option>
            ))}
          </select>
        </label>
        <div className="edit-boolean-actions">
          <button type="button" className="edit-apply-button" disabled={!canApplyBoolean} onClick={applyBoolean('fuse')}>
            Fuse Body
          </button>
          <button type="button" className="edit-apply-button" disabled={!canApplyBoolean} onClick={applyBoolean('cut')}>
            Cut Body
          </button>
        </div>
      </div>
      <div className="edit-controls-section">
        <label className="edit-select-field">
          <span>Split Axis</span>
          <select
            aria-label={`${entityId} split axis`}
            value={splitAxisId}
            onChange={(event) => setSplitAxisId(event.target.value)}
          >
            {HOLE_AXES.map((axis) => (
              <option key={axis.id} value={axis.id}>{axis.label}</option>
            ))}
          </select>
        </label>
        <button type="button" className="edit-apply-button" disabled={Boolean(saving)} onClick={splitBody}>
          Split Body
        </button>
      </div>
    </div>
  )
}

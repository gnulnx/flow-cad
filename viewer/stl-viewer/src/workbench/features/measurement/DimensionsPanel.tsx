import type { Bounds3 } from '../../contracts'
import { formatMm } from './measurement'

export interface DisplayBounds {
  selected: Bounds3 | null
  visible: Bounds3 | null
  selectedPartUuid: string | null
}

export function boundsDimensions(bounds: Bounds3): [number, number, number] {
  return bounds.max.map((value, axis) => Math.max(0, value - bounds.min[axis])) as [number, number, number]
}

export function DimensionsPanel({ bounds, scope, onScope, loading }: {
  bounds: Bounds3 | null
  scope: 'selected' | 'visible'
  onScope(scope: 'selected' | 'visible'): void
  loading: boolean
}) {
  const dimensions = bounds ? boundsDimensions(bounds) : null
  return <aside className="dimensions-panel" aria-label="Dimensions">
    <strong>Dimensions</strong>
    <label>Scope <select aria-label="Dimension scope" value={scope} onChange={(event) => onScope(event.target.value as 'selected' | 'visible')}>
      <option value="selected">Selected part</option><option value="visible">All visible parts</option>
    </select></label>
    {dimensions ? <dl>{['Width · X', 'Depth · Y', 'Height · Z'].map((label, axis) =>
      <div key={label}><dt>{label}</dt><dd>{formatMm(dimensions[axis])}</dd></div>)}</dl>
      : <span>Select a visible part.</span>}
    <small>Display bounds · approximate · world axes</small>
    {loading ? <small>Loading parts — dimensions are incomplete.</small> : null}
  </aside>
}

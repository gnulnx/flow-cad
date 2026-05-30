import type { RotationMode } from '../types'

interface ToolbarProps {
  onFitToView: () => void
  onFrameSelected: () => void
  onReload: () => void
  statusMessage: string
  rotationMode: RotationMode
  onRotationModeChange: (mode: RotationMode) => void
  tapeMode: boolean
  onTapeModeChange: (enabled: boolean) => void
  onClearMeasurements: () => void
  projectName?: string | null
}

const ROTATION_MODE_LABELS: Record<RotationMode, string> = {
  turntable: 'Turntable',
  arcball: 'Arcball',
  free_orbit: 'Free Orbit',
}

export default function Toolbar({
  onFitToView,
  onFrameSelected,
  onReload,
  statusMessage,
  rotationMode,
  onRotationModeChange,
  tapeMode,
  onTapeModeChange,
  onClearMeasurements,
  projectName,
}: ToolbarProps) {
  return (
    <div className="viewer-toolbar">
      <h1 className="viewer-toolbar-title">
        <span>{projectName || 'FlowCAD'}</span> — 3D Viewer
      </h1>
      <div className="toolbar-status">{statusMessage}</div>
      <div className="viewer-toolbar-menu">
        <label className="toolbar-field">
          <span>Navigation</span>
          <select
            value={rotationMode}
            onChange={(event) => onRotationModeChange(event.target.value as RotationMode)}
          >
            {(Object.keys(ROTATION_MODE_LABELS) as RotationMode[]).map((mode) => (
              <option key={mode} value={mode}>{ROTATION_MODE_LABELS[mode]}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="viewer-toolbar-actions">
        <button onClick={onReload} className="btn-tool">Reload</button>
        <button onClick={onFitToView} className="btn-tool">Fit to View</button>
        <button onClick={onFrameSelected} className="btn-tool">Frame Selected</button>
        <button
          aria-pressed={tapeMode}
          title="Tape Tool"
          onClick={() => onTapeModeChange(!tapeMode)}
          className={`btn-tool ${tapeMode ? 'active' : ''}`}
        >
          Tape
        </button>
        <button onClick={onClearMeasurements} className="btn-tool">Clear Measurements</button>
        <button className="btn-tool" onClick={() => {
          const input = document.getElementById('file-input') as HTMLInputElement
          input.click()
        }}>Open File</button>
      </div>
    </div>
  )
}

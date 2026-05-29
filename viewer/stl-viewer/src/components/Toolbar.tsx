import type { RotationMode } from '../types'

interface ToolbarProps {
  onFitToView: () => void
  onFrameSelected: () => void
  onReload: () => void
  statusMessage: string
  rotationMode: RotationMode
  onRotationModeChange: (mode: RotationMode) => void
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
}: ToolbarProps) {
  return (
    <div className="viewer-toolbar" style={{
      padding: '10px 16px',
      background: '#16213e',
      borderBottom: '1px solid #0f3460',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      flexWrap: 'wrap',
      gap: '8px',
      flexShrink: 0,
    }}>
      <h1 style={{ fontSize: '15px', fontWeight: 600, color: '#e94560', flex: '1 1 190px' }}>ErB Balance Bot — 3D Viewer</h1>
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
      <div className="viewer-toolbar-actions" style={{ display: 'flex', gap: '8px', flex: '0 0 auto' }}>
        <button onClick={onReload} style={{
          background: '#0f3460',
          color: '#e0e0e0',
          border: '1px solid #1a5276',
          padding: '6px 14px',
          borderRadius: '4px',
          cursor: 'pointer',
          fontSize: '12px',
        }}>Reload</button>
        <button onClick={onFitToView} style={{
          background: '#0f3460',
          color: '#e0e0e0',
          border: '1px solid #1a5276',
          padding: '6px 14px',
          borderRadius: '4px',
          cursor: 'pointer',
          fontSize: '12px',
        }}>Fit to View</button>
        <button onClick={onFrameSelected} style={{
          background: '#0f3460',
          color: '#e0e0e0',
          border: '1px solid #1a5276',
          padding: '6px 14px',
          borderRadius: '4px',
          cursor: 'pointer',
          fontSize: '12px',
        }}>Frame Selected</button>
        <button style={{
          background: '#0f3460',
          color: '#e0e0e0',
          border: '1px solid #1a5276',
          padding: '6px 14px',
          borderRadius: '4px',
          cursor: 'pointer',
          fontSize: '12px',
        }} onClick={() => {
          const input = document.getElementById('file-input') as HTMLInputElement
          input.click()
        }}>Open File</button>
      </div>
    </div>
  )
}

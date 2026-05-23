interface ToolbarProps {
  onFitToView: () => void
}

export default function Toolbar({ onFitToView }: ToolbarProps) {
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
      <div className="viewer-toolbar-actions" style={{ display: 'flex', gap: '8px', flex: '0 0 auto' }}>
        <button onClick={onFitToView} style={{
          background: '#0f3460',
          color: '#e0e0e0',
          border: '1px solid #1a5276',
          padding: '6px 14px',
          borderRadius: '4px',
          cursor: 'pointer',
          fontSize: '12px',
        }}>Fit to View</button>
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

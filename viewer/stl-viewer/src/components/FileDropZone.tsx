import type { ReactNode } from 'react'

interface FileDropZoneProps {
  children: ReactNode
  onDrop: (e: React.DragEvent) => void
  onDragOver: (e: React.DragEvent) => void
  onDragLeave: (e: React.DragEvent) => void
  onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void
  isDragOver: boolean
}

export default function FileDropZone({ children, onDrop, onDragOver, onDragLeave, onFileSelect, isDragOver }: FileDropZoneProps) {
  return (
    <div
      data-testid="drop-zone"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      style={{
        flex: 1,
        height: '100%',
        width: '100%',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <input
        type="file"
        accept=".stl"
        multiple
        onChange={onFileSelect}
        style={{ display: 'none' }}
        id="file-input"
      />
      
      {/* Glassmorphic File Drag Overlay */}
      <div className={`drag-overlay ${isDragOver ? 'active' : ''}`}>
        <div className="drag-overlay-box">
          <div className="drag-overlay-icon">📁</div>
          <div className="drag-overlay-title">Drop STL Mesh File</div>
          <div className="drag-overlay-text">
            Drop your generated STL files here to instantly load and inspect them in 3D space.
          </div>
        </div>
      </div>
      
      {children}
    </div>
  )
}

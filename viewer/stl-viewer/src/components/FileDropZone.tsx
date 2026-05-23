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
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      style={{
        flex: 1,
        position: 'relative',
        border: isDragOver ? '2px solid #e94560' : '2px dashed #0f3460',
        borderRadius: '8px',
        margin: '16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 0.2s',
        background: isDragOver ? 'rgba(233,69,96,0.05)' : 'transparent',
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
      {children}
    </div>
  )
}

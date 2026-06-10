import { useEffect, useMemo, useRef, useState } from 'react'
import { VIEWER_SHORTCUTS } from '../shortcuts'
import type { RotationMode } from '../types'

interface ToolbarProps {
  onFitToView: () => void
  onFrameSelected: () => void
  onReload: () => void
  statusMessage: string
  rotationMode: RotationMode
  onRotationModeChange: (mode: RotationMode) => void
  onTapeModeChange: (enabled: boolean) => void
  tapeMode: boolean
  onClearMeasurements: () => void
  onOpen: () => void
  markupMode: boolean
  onMarkupModeToggle: () => void
  projectName?: string | null
}

const ROTATION_MODE_LABELS: Record<RotationMode, string> = {
  turntable: 'Turntable',
  arcball: 'Arcball',
  free_orbit: 'Free Orbit',
}

type OpenMenu = 'file' | 'edit' | 'view' | null

export default function Toolbar({
  onFitToView,
  onFrameSelected,
  onReload,
  statusMessage,
  rotationMode,
  onRotationModeChange,
  onTapeModeChange,
  tapeMode,
  onClearMeasurements,
  onOpen,
  markupMode,
  onMarkupModeToggle,
  projectName,
}: ToolbarProps) {
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null)
  const menuRef = useRef<HTMLElement>(null)

  const allModes = useMemo(() => {
    return Object.keys(ROTATION_MODE_LABELS) as RotationMode[]
  }, [])

  useEffect(() => {
    const closeMenu = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpenMenu(null)
      }
    }

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpenMenu(null)
      }
    }

    window.addEventListener('pointerdown', closeMenu)
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      window.removeEventListener('pointerdown', closeMenu)
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [])

  const handleMenuOpen = (menu: OpenMenu) => {
    setOpenMenu((current) => (current === menu ? null : menu))
  }

  return (
    <header className="viewer-toolbar" ref={menuRef}>
      <h1 className="viewer-toolbar-title">
        <span>{projectName || 'FlowCAD'}</span> — 3D Viewer
      </h1>
      <nav className="viewer-menu" aria-label="Viewer top menu">
        <div className="menu-group">
          <button
            type="button"
            className="menu-button"
            onClick={() => handleMenuOpen('file')}
            aria-expanded={openMenu === 'file'}
          >
            File
          </button>
          {openMenu === 'file' ? (
            <div className="menu-panel" role="menu" aria-label="File menu">
              <button
                type="button"
                role="menuitem"
                className="btn-tool"
                onClick={() => {
                  onOpen()
                  setOpenMenu(null)
                }}
              >
                Open
              </button>
            </div>
          ) : null}
        </div>

        <div className="menu-group">
          <button
            type="button"
            className="menu-button"
            onClick={() => handleMenuOpen('edit')}
            aria-expanded={openMenu === 'edit'}
          >
            Edit
          </button>
          {openMenu === 'edit' ? (
            <div className="menu-panel" role="menu" aria-label="Edit menu">
              <button
                type="button"
                role="menuitem"
                aria-label="Annotate"
                aria-pressed={markupMode}
                className={`btn-tool menu-item-with-shortcut ${markupMode ? 'active' : ''}`}
                onClick={() => {
                  onMarkupModeToggle()
                  setOpenMenu(null)
                }}
              >
                <span>Annotate</span>
                <span className="menu-shortcut">{VIEWER_SHORTCUTS.toggleAnnotations.label}</span>
              </button>
            </div>
          ) : null}
        </div>

        <div className="menu-group">
          <button
            type="button"
            className="menu-button"
            onClick={() => handleMenuOpen('view')}
            aria-expanded={openMenu === 'view'}
          >
            View
          </button>
          {openMenu === 'view' ? (
            <div className="menu-panel" role="menu" aria-label="View menu">
              <label className="toolbar-field" aria-label="Navigation mode">
                <span>Navigation mode</span>
                <select
                  value={rotationMode}
                  onChange={(event) => onRotationModeChange(event.target.value as RotationMode)}
                  aria-label="Navigation mode"
                >
                  {allModes.map((mode) => (
                    <option key={mode} value={mode}>{ROTATION_MODE_LABELS[mode]}</option>
                  ))}
                </select>
              </label>
              <button onClick={() => { onFitToView(); setOpenMenu(null) }} className="btn-tool" type="button">Fit to View</button>
              <button onClick={() => { onReload(); setOpenMenu(null) }} className="btn-tool" type="button">Reload</button>
              <button onClick={() => { onFrameSelected(); setOpenMenu(null) }} className="btn-tool" type="button">Frame Selected</button>
              <button
                type="button"
                className={`btn-tool ${tapeMode ? 'active' : ''}`}
                onClick={() => {
                  onTapeModeChange(!tapeMode)
                  setOpenMenu(null)
                }}
              >
                Tape
              </button>
              <button
                type="button"
                className="btn-tool"
                onClick={() => {
                  onClearMeasurements()
                  setOpenMenu(null)
                }}
              >
                Clear Measurements
              </button>
            </div>
          ) : null}
        </div>
      </nav>
      <div className="toolbar-status">{statusMessage}</div>
    </header>
  )
}

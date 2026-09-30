import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export type ContextAction = 'hide' | 'isolate' | 'frame' | 'undo' | 'show-all'

interface Props {
  clientX: number
  clientY: number
  label: string | null
  canUndo: boolean
  hasHidden: boolean
  onAction(action: ContextAction): void
  onClose(): void
}

export function ComponentContextMenu({ clientX, clientY, label, canUndo, hasHidden, onAction, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ left: clientX, top: clientY })
  useLayoutEffect(() => {
    const bounds = ref.current?.getBoundingClientRect()
    if (bounds) setPosition({
      left: Math.max(8, Math.min(clientX, window.innerWidth - bounds.width - 8)),
      top: Math.max(8, Math.min(clientY, window.innerHeight - bounds.height - 8)),
    })
    const focusTarget = ref.current?.querySelector<HTMLButtonElement>('button:not(:disabled)') ?? ref.current
    focusTarget?.focus()
  }, [clientX, clientY, label])
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) onClose() }
    window.addEventListener('pointerdown', outside, true)
    window.addEventListener('resize', onClose)
    window.addEventListener('blur', onClose)
    return () => {
      window.removeEventListener('pointerdown', outside, true)
      window.removeEventListener('resize', onClose)
      window.removeEventListener('blur', onClose)
    }
  }, [onClose])
  const run = (action: ContextAction) => { onAction(action); onClose() }
  return createPortal(<div ref={ref} role="menu" tabIndex={-1} aria-label="Part actions" className="component-context-menu" style={position}
    onContextMenu={(event) => event.preventDefault()} onPointerDown={(event) => event.stopPropagation()}
    onKeyDown={(event) => {
      event.stopPropagation()
      if (event.key === 'Escape' || event.key === 'Tab') { onClose(); return }
      if (!event.ctrlKey && !event.metaKey && !event.altKey) {
        const action: ContextAction | null = event.key === 'H' && hasHidden ? 'show-all'
          : event.key === 'h' && label ? 'hide' : event.key.toLowerCase() === 'i' && label ? 'isolate'
            : event.key.toLowerCase() === 'u' && canUndo ? 'undo' : null
        if (action) { event.preventDefault(); run(action); return }
      }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
      event.preventDefault()
      const buttons = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
        : (index + (event.key === 'ArrowUp' ? -1 : 1) + buttons.length) % buttons.length
      buttons[next]?.focus()
    }}>
    <div className="component-context-menu__title">{label ?? 'View actions'}</div>
    {label ? <>
      <button type="button" role="menuitem" onClick={() => run('hide')}>Hide part <kbd>H</kbd></button>
      <button type="button" role="menuitem" onClick={() => run('isolate')}>Isolate part <kbd>I</kbd></button>
      <button type="button" role="menuitem" onClick={() => run('frame')}>Frame part</button>
      <hr />
    </> : null}
    <button type="button" role="menuitem" disabled={!canUndo} onClick={() => run('undo')}>Undo visibility <kbd>U</kbd></button>
    <button type="button" role="menuitem" disabled={!hasHidden} onClick={() => run('show-all')}>Show all <kbd>⇧ H</kbd></button>
  </div>, document.body)
}

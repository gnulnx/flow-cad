import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  label: string
  x: number
  y: number
  onDelete(): void
  onClose(): void
}

export function PartDeleteMenu({ label, x, y, onDelete, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ left: x, top: y })
  useLayoutEffect(() => {
    const box = ref.current?.getBoundingClientRect()
    if (box) setPosition({ left: Math.max(8, Math.min(x, innerWidth - box.width - 8)),
      top: Math.max(8, Math.min(y, innerHeight - box.height - 8)) })
    ref.current?.querySelector('button')?.focus()
  }, [x, y])
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) onClose() }
    window.addEventListener('pointerdown', outside, true)
    window.addEventListener('blur', onClose)
    return () => { window.removeEventListener('pointerdown', outside, true); window.removeEventListener('blur', onClose) }
  }, [onClose])
  return createPortal(<div ref={ref} role="menu" aria-label={`Actions for ${label}`}
    className="component-context-menu" style={position}
    onContextMenu={(event) => event.preventDefault()}
    onKeyDown={(event) => { if (event.key === 'Escape' || event.key === 'Tab') { event.stopPropagation(); onClose() } }}>
    <div className="component-context-menu__title">{label}</div>
    <button type="button" role="menuitem" onClick={onDelete}>Delete part</button>
  </div>, document.body)
}

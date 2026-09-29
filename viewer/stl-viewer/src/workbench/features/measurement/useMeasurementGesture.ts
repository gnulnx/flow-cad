import { useCallback, useEffect, useRef, useState, type PointerEvent } from 'react'
import type { MeasurementMode, SnapCandidate } from './measurement'

export function useMeasurementGesture({ active, mode, resetKey, snap, commit, exit }: {
  active: boolean
  mode: MeasurementMode
  resetKey: string
  snap(x: number, y: number, start: SnapCandidate | null): SnapCandidate | null
  commit(start: SnapCandidate, end: SnapCandidate, mode: MeasurementMode): void
  exit(): void
}) {
  const [start, setStart] = useState<SnapCandidate | null>(null)
  const [hover, setHover] = useState<SnapCandidate | null>(null)
  const down = useRef<{ x: number; y: number; start: SnapCandidate; finishing: boolean; pointerId: number } | null>(null)
  const cancel = useCallback(() => { down.current = null; setStart(null); setHover(null) }, [])
  useEffect(cancel, [active, mode, resetKey, cancel])
  useEffect(() => {
    const keyDown = (event: KeyboardEvent) => {
      if (!active || event.key !== 'Escape') return
      event.preventDefault()
      if (start || down.current) cancel()
      else exit()
    }
    window.addEventListener('keydown', keyDown)
    return () => window.removeEventListener('keydown', keyDown)
  }, [active, start, cancel, exit])
  const isCanvas = (event: PointerEvent<HTMLDivElement>) => (event.target as Element).tagName === 'CANVAS'
  return {
    start, hover, cancel,
    onPointerDown(event: PointerEvent<HTMLDivElement>) {
      if (!active || event.button !== 0 || !isCanvas(event)) return
      const target = snap(event.clientX, event.clientY, start)
      if (!target) return
      event.preventDefault()
      event.currentTarget.setPointerCapture?.(event.pointerId)
      down.current = { x: event.clientX, y: event.clientY, start: start ?? target, finishing: start !== null, pointerId: event.pointerId }
      if (mode === 'distance') setStart(start ?? target)
      setHover(target)
    },
    onPointerMove(event: PointerEvent<HTMLDivElement>) {
      if (!active || (!down.current && !isCanvas(event))) return
      setHover(snap(event.clientX, event.clientY, down.current?.start ?? start))
    },
    onPointerUp(event: PointerEvent<HTMLDivElement>) {
      const gesture = down.current
      if (!gesture || gesture.pointerId !== event.pointerId || event.button !== 0) return
      down.current = null
      event.currentTarget.releasePointerCapture?.(event.pointerId)
      const target = snap(event.clientX, event.clientY, gesture.start)
      const dragged = Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) >= 4
      if (mode === 'edge_length') {
        if (!dragged && target?.edge) commit(target, target, mode)
        cancel()
      } else if (!dragged && !gesture.finishing && target?.kind === 'line_edge' && target.edge) {
        commit(target, target, 'edge_length')
        cancel()
      } else if (target && (dragged || gesture.finishing)) {
        const distance = Math.hypot(...target.pointMm.map((v, i) => v - gesture.start.pointMm[i]))
        if (distance > 1e-6) { commit(gesture.start, target, mode); setStart(null) }
      }
    },
    onPointerCancel: cancel,
    onPointerLeave() { if (!down.current) setHover(null) },
  }
}

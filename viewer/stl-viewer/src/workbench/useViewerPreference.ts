import { useState } from 'react'

/** Browser display preferences remain usable when storage is disabled. */
export function useViewerPreference(name: string, fallback: boolean) {
  const key = `flow-cad.viewer.${name}`
  const [value, setValue] = useState(() => {
    try {
      const saved = localStorage.getItem(key)
      return saved === null ? fallback : saved === 'true'
    } catch { return fallback }
  })
  const update = (next: boolean) => {
    setValue(next)
    try { localStorage.setItem(key, String(next)) } catch { /* Session-only preference. */ }
  }
  return [value, update] as const
}

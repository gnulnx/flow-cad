export interface ViewerShortcut {
  id: string
  label: string
  key: string
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
  shiftKey?: boolean
}

export const VIEWER_SHORTCUTS = {
  toggleAnnotations: {
    id: 'toggleAnnotations',
    label: 'Ctrl+A',
    key: 'a',
    ctrlKey: true,
  },
} satisfies Record<string, ViewerShortcut>

export function matchesViewerShortcut(event: KeyboardEvent, shortcut: ViewerShortcut) {
  return event.key.toLowerCase() === shortcut.key.toLowerCase()
    && Boolean(event.ctrlKey) === Boolean(shortcut.ctrlKey)
    && Boolean(event.metaKey) === Boolean(shortcut.metaKey)
    && Boolean(event.altKey) === Boolean(shortcut.altKey)
    && Boolean(event.shiftKey) === Boolean(shortcut.shiftKey)
}

export function isTextEntryTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tagName = target.tagName.toLowerCase()
  return tagName === 'input' || tagName === 'textarea' || tagName === 'select'
}

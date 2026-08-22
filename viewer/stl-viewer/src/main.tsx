import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import AppShell from './workbench/AppShell'

declare global {
  interface Window {
    THREE: typeof import('three')
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppShell />
  </StrictMode>,
)

import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { WorkbenchPart } from '../../contracts'
import { PartFileActions } from './PartFileActions'

afterEach(() => vi.unstubAllGlobals())

const part = (key = 'cover') => ({ key, downloads: ['step', 'stl'].map(kind => ({
  kind, url: `http://localhost:8001/models/${key}-${kind}?download=true`, filename: `${key}.${kind}`,
})) } as WorkbenchPart)

function nativeClick(link: HTMLElement) {
  let intercepted: boolean | undefined
  // Observe React's event handling, then stop jsdom's unsupported navigation.
  document.addEventListener('click', (event) => {
    intercepted = event.defaultPrevented
    event.preventDefault()
  }, { once: true })
  fireEvent.click(link)
  return intercepted === false
}

it('downloads STL through native navigation even when JavaScript fetch would fail', () => {
  const fetcher = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
  vi.stubGlobal('fetch', fetcher)
  render(<PartFileActions part={part()} />)
  const link = screen.getByRole('link', { name: 'Download STL' })
  expect(nativeClick(link)).toBe(true)
  expect(fetcher).not.toHaveBeenCalled()
  expect(link).toHaveAttribute('download', 'cover.stl')
})

it('downloads STEP through its own native attachment URL', () => {
  const fetcher = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
  vi.stubGlobal('fetch', fetcher)
  render(<PartFileActions part={part()} />)
  const link = screen.getByRole('link', { name: 'Download STEP' })
  expect(nativeClick(link)).toBe(true)
  expect(link).toHaveAttribute('href', 'http://localhost:8001/models/cover-step?download=true')
  expect(link).toHaveAttribute('download', 'cover.step')
  expect(fetcher).not.toHaveBeenCalled()
})

it('rebinds both download URLs and filenames when a different part is selected', () => {
  const view = render(<PartFileActions part={part('first')} />)
  view.rerender(<PartFileActions part={part('second')} />)
  for (const kind of ['step', 'stl']) {
    const link = screen.getByRole('link', { name: `Download ${kind.toUpperCase()}` })
    expect(link).toHaveAttribute('href', `http://localhost:8001/models/second-${kind}?download=true`)
    expect(link).toHaveAttribute('download', `second.${kind}`)
  }
})

it('allows repeated STL downloads without a stuck busy state or intercepted clicks', () => {
  const fetcher = vi.fn(() => new Promise(() => {}))
  vi.stubGlobal('fetch', fetcher)
  render(<PartFileActions part={part()} />)
  const link = screen.getByRole('link', { name: 'Download STL' })
  for (let index = 0; index < 3; index++) expect(nativeClick(link)).toBe(true)
  expect(link).not.toHaveAttribute('aria-disabled', 'true')
  expect(fetcher).not.toHaveBeenCalled()
})

it('allows STEP and STL downloads consecutively without blocking one another', () => {
  const fetcher = vi.fn(() => new Promise(() => {}))
  vi.stubGlobal('fetch', fetcher)
  render(<PartFileActions part={part()} />)
  expect(nativeClick(screen.getByRole('link', { name: 'Download STL' }))).toBe(true)
  expect(nativeClick(screen.getByRole('link', { name: 'Download STEP' }))).toBe(true)
  expect(fetcher).not.toHaveBeenCalled()
})

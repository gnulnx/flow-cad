import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SourcePanel from './SourcePanel'
import type { SourceContext } from '../types'

function sourceContext(overrides: Partial<SourceContext> = {}): SourceContext {
  return {
    component_id: 'wheel_box_test_body',
    symbol: 'make_wheel_box_test_body',
    file_path: '/repo/src/flow_cad/parts/wheel_box/prototype.py',
    relative_file_path: 'src/flow_cad/parts/wheel_box/prototype.py',
    start_line: 1,
    end_line: 5,
    highlight_start_line: 2,
    highlight_end_line: 3,
    language: 'python',
    content: [
      'from flow_cad.params import ChassisParams',
      'def make_wheel_box_test_body(params: ChassisParams):',
      '    return 42',
      '',
      'def make_wheel_box_test_top_lid(params: ChassisParams):',
    ].join('\n'),
    excerpt: '',
    ...overrides,
  }
}

function expectSourceText(container: HTMLElement, text: string) {
  expect(container.querySelector('.source-code')?.textContent).toContain(text)
}

describe('SourcePanel', () => {
  it('renders full source content with generated line numbers and the active range highlighted', () => {
    const { container } = render(
      <SourcePanel
        context={sourceContext()}
        activeId="wheel_box_test_body"
        collapsed={false}
        onToggle={vi.fn()}
      />,
    )

    expect(screen.getByText('src/flow_cad/parts/wheel_box/prototype.py')).toBeInTheDocument()
    expectSourceText(container, 'make_wheel_box_test_body')
    expectSourceText(container, 'make_wheel_box_test_top_lid')
    expect(Array.from(container.querySelectorAll('.source-line-number')).map((node) => node.textContent)).toEqual([
      '1',
      '2',
      '3',
      '4',
      '5',
    ])
    expect(container.querySelectorAll('.source-line-highlight')).toHaveLength(2)
    expect(container.querySelectorAll('.syntax-keyword').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('.syntax-number').length).toBeGreaterThan(0)
  })

  it('falls back to legacy numbered excerpts when full content is not present', () => {
    const context = sourceContext({
      content: undefined,
      highlight_start_line: 10,
      highlight_end_line: 10,
      excerpt: '  9: class Sample:\n  10:     pass',
    })

    const { container } = render(
      <SourcePanel
        context={context}
        activeId="sample"
        collapsed={false}
        onToggle={vi.fn()}
      />,
    )

    expect(Array.from(container.querySelectorAll('.source-line-number')).map((node) => node.textContent)).toEqual([
      '9',
      '10',
    ])
    expect(container.querySelectorAll('.source-line-highlight')).toHaveLength(1)
    expectSourceText(container, 'Sample')
  })

  it('keeps the header available when collapsed', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()

    render(
      <SourcePanel
        context={sourceContext()}
        activeId="wheel_box_test_body"
        collapsed={true}
        onToggle={onToggle}
      />,
    )

    expect(screen.getByRole('button', { name: 'Source' })).toBeInTheDocument()
    expect(screen.queryByText('src/flow_cad/parts/wheel_box/prototype.py')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Source' }))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })
})

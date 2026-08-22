import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CodexConnectionSettings } from './CodexConnectionSettings'

describe('CodexConnectionSettings', () => {
  it('shows bounded readiness facts, setup commands, and a retry action', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<CodexConnectionSettings
      status={{
        provider: 'codex-app-server',
        available: true,
        status: 'ready',
        diagnostics: {
          executableAvailable: true,
          authenticated: true,
          authMethod: 'chatgpt',
          lastFailureReason: 'rpc_error',
          lastRpcMethod: 'turn/start',
        },
      }}
      onRetry={onRetry}
      onClose={() => undefined}
    />)

    expect(screen.getByText('Needs attention')).toBeInTheDocument()
    expect(screen.getByText('Signed in with chatgpt')).toBeInTheDocument()
    expect(screen.getByText('rpc_error at turn/start')).toBeInTheDocument()
    expect(screen.getByText('codex login')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /official Codex authentication guide/ })).toHaveAttribute('href', 'https://developers.openai.com/codex/auth/')
    await user.click(screen.getByRole('button', { name: 'Recheck' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})

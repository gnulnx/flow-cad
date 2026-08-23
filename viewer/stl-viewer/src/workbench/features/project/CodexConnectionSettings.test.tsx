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
    expect(screen.getByLabelText('Flow CAD MCP setup command')).toHaveTextContent('FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS=/path/to/flow-cad:/path/to/flow-project')
    expect(screen.getByText('codex mcp list')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /official Codex authentication guide/ })).toHaveAttribute('href', 'https://developers.openai.com/codex/auth/')
    expect(screen.getByRole('link', { name: /official Codex MCP guide/ })).toHaveAttribute('href', 'https://learn.chatgpt.com/docs/extend/mcp?surface=cli')
    await user.click(screen.getByRole('button', { name: 'Recheck' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})

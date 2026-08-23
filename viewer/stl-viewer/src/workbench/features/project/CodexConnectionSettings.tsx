import type { ChatProviderStatus } from '../../contracts'

interface CodexConnectionSettingsProps {
  status: ChatProviderStatus | null
  onRetry(): void
  onClose(): void
}

function fact(value: boolean | null | undefined, ready: string, missing: string) {
  if (value === undefined || value === null) return 'Checking…'
  return value ? ready : missing
}

export function CodexConnectionSettings({ status, onRetry, onClose }: CodexConnectionSettingsProps) {
  const diagnostics = status?.diagnostics
  const lastFailure = diagnostics?.lastFailureReason
  const connectionLabel = !status
    ? 'Checking'
    : status.available && !lastFailure
      ? 'Connected'
      : status.available
        ? 'Needs attention'
        : 'Setup required'

  return (
    <div className="settings-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <section className="connection-settings" role="dialog" aria-modal="true" aria-labelledby="connection-settings-title">
        <header>
          <div>
            <span className="eyebrow">Workbench settings</span>
            <h2 id="connection-settings-title">Codex connection</h2>
          </div>
          <button type="button" className="settings-close" onClick={onClose} aria-label="Close settings">×</button>
        </header>

        <div className="connection-state" data-state={connectionLabel.toLocaleLowerCase().replace(' ', '-')}>
          <span className={`health-dot ${status?.available && !lastFailure ? 'health-dot--ready' : 'health-dot--error'}`} />
          <div>
            <strong>{connectionLabel}</strong>
            <span>{status?.provider ?? 'Codex app server'}</span>
          </div>
          <button type="button" className="tool-button" onClick={onRetry}>Recheck</button>
        </div>

        <dl className="connection-facts">
          <div><dt>CLI</dt><dd>{fact(diagnostics?.executableAvailable, 'Found on PATH', 'Not found on PATH')}</dd></div>
          <div><dt>Authentication</dt><dd>{fact(diagnostics?.authenticated, diagnostics?.authMethod ? `Signed in with ${diagnostics.authMethod}` : 'Signed in', 'Not signed in')}</dd></div>
          <div><dt>Permissions</dt><dd>Read-only · approvals disabled</dd></div>
          {lastFailure ? <div className="connection-facts__warning"><dt>Last turn</dt><dd>{lastFailure}{diagnostics?.lastRpcMethod ? ` at ${diagnostics.lastRpcMethod}` : ''}</dd></div> : null}
        </dl>

        <div className="connection-setup">
          <h3>1. Connect workbench chat</h3>
          <ol>
            <li>Open a terminal on this machine.</li>
            <li>Run <code>codex login</code> and finish the browser sign-in.</li>
            <li>Confirm it with <code>codex login status</code>, then choose Recheck here.</li>
          </ol>
          <p>For a headless machine, use <code>codex login --device-auth</code>. API-key users can pipe <code>OPENAI_API_KEY</code> to <code>codex login --with-api-key</code>.</p>
          <p className="connection-secret-note">Flow CAD never stores or accepts the credential in project settings; it reuses the local Codex credential store.</p>
          <a href="https://developers.openai.com/codex/auth/" target="_blank" rel="noreferrer">Open official Codex authentication guide ↗</a>
        </div>

        <div className="connection-setup">
          <h3>2. Connect Codex agent tools</h3>
          <p>Add Flow CAD as a local MCP server so Codex can inspect the active viewport, run validators, and use project-scoped draft tools.</p>
          <pre aria-label="Flow CAD MCP setup command"><code>{`codex mcp add flow-cad \\
  --env FLOW_CAD_PROJECT_ROOT=/path/to/flow-project \\
  --env FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS=/path/to/flow-cad:/path/to/flow-project \\
  --env FLOW_CAD_MCP_TOOLSET=default \\
  -- flow-cad-mcp`}</code></pre>
          <ol>
            <li>Replace both example paths with the runtime and project repository paths.</li>
            <li>Run <code>codex mcp list</code> to confirm the server, then restart Codex so it receives the new root policy.</li>
            <li>Use <code>:</code> between allowed roots on Linux or macOS; use <code>;</code> on Windows.</li>
          </ol>
          <p className="connection-secret-note">Allowed roots are an access boundary. Add only repositories that Codex should be able to inspect or change.</p>
          <a href="https://learn.chatgpt.com/docs/extend/mcp?surface=cli" target="_blank" rel="noreferrer">Open official Codex MCP guide ↗</a>
        </div>
      </section>
    </div>
  )
}

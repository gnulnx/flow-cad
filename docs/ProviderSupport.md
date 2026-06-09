# Model Provider Support Plan

Date: 2026-06-09

## Purpose

Flow CAD should let users connect the model provider that fits a practical CAD
workflow without becoming a general-purpose model marketplace. The design-thread
chat surface should eventually feel like a normal model-backed CAD workspace:
pick a supported provider, authenticate or point at a local endpoint, choose a
model, test it, and then use it for viewport-aware chat with CAD-safe tools.

The target user experience is intentionally close to Hermes Agent's provider
setup:

```bash
flow model
flow model status
flow model providers
flow model list <provider> --refresh
flow model login <provider>
flow model use <provider>/<model>
flow model test
flow model fallback add <provider>/<model>
```

`flow model` should become the durable model configuration path for the viewer,
MCP-backed design threads, and future worker packets.

## Direction

Use a Hermes Agent style model-provider foundation rather than a one-off
LlamaStudio-only adapter, but keep the supported provider set deliberately
small.

Hermes has already solved much of the hard, boring provider work:

- interactive provider selection
- provider aliases and canonical provider ids
- direct API, OAuth, device-login, local-server, and custom-endpoint setup flows
- model discovery and cached live model lists
- provider-specific validation fallbacks when `/models` is missing or incomplete
- OpenAI-compatible, Anthropic-compatible, native, and custom transport decisions
- fallback provider chains
- config/secrets separation and atomic writes
- local provider probing for desktop/server runtimes

Flow CAD should borrow that work aggressively where the license and code shape
allow it, but should not inherit Hermes' full provider-support burden. The
preferred approach is to copy or adapt focused modules into a small Flow CAD
provider subsystem, preserving upstream MIT attribution where source is copied,
rather than taking a large runtime dependency on all of Hermes.

The product line is:

> Flow CAD provides a reliable model-provider foundation and first-class support
> for the model stacks most useful to CAD work. It is not trying to become a
> full Hermes replacement or a universal LLM router.

## License Note

Hermes Agent currently declares the MIT license in
`/home/gnulnx/hermes-agent/LICENSE`.

This Flow CAD checkout does not currently have a top-level `LICENSE` file or a
`project.license` entry in `pyproject.toml`. Before copying substantial Hermes
source into this repository, confirm Flow CAD's intended license and add a
project-level license/notice strategy. Any copied Hermes source must preserve the
required MIT copyright and permission notice.

Small patterns can be reimplemented directly. Larger copied functions, auth
flows, or provider tables should either carry module-level attribution or be
listed in a `THIRD_PARTY_NOTICES.md` file.

## Supported Provider Policy

Flow CAD should have a broad provider architecture and a narrow support promise.

### Tier 1: First-Class And Tested

These providers are the first product slice. They should have docs, tests,
diagnostics, and a validation path before being presented as fully supported:

- `openai`: direct OpenAI API key through the current supported API surface.
- `openai-codex`: Codex/ChatGPT account style auth where Hermes code can be
  reused cleanly and legally.
- `gemini`: Google Gemini API key support.
- `llamastudio`: the LlamaStudio application/runtime. This is a BLR-local
  runtime worth integrating as a named provider, not just an anonymous URL.
- `lmstudio`: LM Studio, the desktop local-model app with a model server.
- `local-openai-compatible`: custom or local OpenAI-compatible endpoint. This is
  the catch-all for llama.cpp, vLLM, many hosted gateways, and other compatible
  runtimes.
- `openrouter`: hosted aggregator support through its OpenAI-compatible API.

### Tier 2: Beta Until Validated

- `anthropic`: strategically important, but beta until Flow CAD has a real API
  key validation path or a regular maintainer using it.

Tier 2 providers can have mocked contract tests and optional live tests gated by
environment variables. They should be labeled beta in CLI/status output until
someone can regularly validate them.

### Explicitly Out Of Scope For The First Slice

Do not implement Hermes parity in the first Flow CAD provider pass:

- Bedrock, Azure Foundry, xAI, Qwen/DashScope, DeepSeek, Mistral, Novita, Nous,
  MiniMax, Moonshot/Kimi, GitHub Copilot, native Ollama, and other long-tail
  providers.
- Provider-specific OAuth flows that no active Flow CAD maintainer can validate.
- Provider-specific routing features that do not affect viewport-aware CAD chat.

The architecture should make those providers possible later. The product should
not promise them until there is user demand and a validation path.

## Provider Profile Model

Add a reusable provider-profile layer under `src/flow_cad/`, for example:

```text
src/flow_cad/model_providers/
  __init__.py
  profiles.py
  registry.py
  config.py
  auth.py
  discovery.py
  runtime.py
  cli.py
  providers/
    llamastudio.py
    lmstudio.py
    openai.py
    openai_codex.py
    gemini.py
    local_openai_compatible.py
    openrouter.py
    anthropic_beta.py
```

A provider profile should be declarative enough that adding a simple provider
does not require editing the chat runtime:

```text
ProviderProfile
  id
  display_name
  aliases
  support_tier
  validation_status
  group
  provider_kind
  transport
  auth_mode
  base_url
  base_url_env_var
  api_key_env_var
  models_url
  default_models
  setup_strategy
  discovery_strategy
  health_strategy
  runtime_strategy
  capabilities
```

Use capability metadata to decide how the provider can participate in CAD chat:

- streaming output
- text input
- image input or screenshot support
- tool calling
- structured output
- reasoning effort controls
- local/offline operation
- context window
- max output tokens
- model listing support
- custom endpoint support
- CAD-safe tool compatibility
- validation status

Flow CAD should warn clearly when the selected model cannot consume viewport
screenshots directly. Text-only models are still useful because the backend can
send selected parts, visible parts, measurements, annotations, and attachment
metadata as text/JSON context.

## Storage

Model configuration is user-local by default. Project repos should not receive
secrets or account tokens.

Suggested storage:

```text
$FLOW_CAD_HOME/
  config.json
  model-profiles.json
  model-cache/
    <provider>.json
  auth/
    <provider>.json
```

If `FLOW_CAD_HOME` is unset, use `~/.flow-cad/` for the first implementation to
avoid adding another dependency. A later pass can adopt XDG directories if needed.

Project-specific overrides can live under `.flow/`:

```text
.flow/model-profile.json
```

Rules:

- User secrets and OAuth tokens stay in the user-local auth store.
- Project overrides may select a provider/model/profile name, but must not store
  secrets.
- Environment variables remain an escape hatch and should override disk config
  for CI and temporary testing.
- Atomic writes are required for config, auth, and cache files.
- Corrupt config should be backed up and reported with a clear recovery message.

## CLI UX

The initial command group should support both interactive and scriptable use.

```bash
flow model
flow model status
flow model providers
flow model providers --all
flow model list <provider>
flow model list <provider> --refresh
flow model login <provider>
flow model use <provider>/<model>
flow model use <provider>/<model> --reasoning medium
flow model use <provider>/<model> --project
flow model test
flow model test --message "Say hello from Flow CAD"
flow model doctor
flow model fallback list
flow model fallback add <provider>/<model>
flow model fallback remove <provider>/<model>
flow model fallback clear
```

Interactive `flow model` should:

1. Show the active provider/model first.
2. Show Tier 1 providers by default.
3. Hide beta/experimental providers unless the user asks for them.
4. Highlight first-class local options: LlamaStudio and LM Studio.
5. Prompt for only the credentials needed by the chosen provider.
6. Fetch or display model choices.
7. Save the active model profile.
8. Run an optional test prompt before returning success.

The CLI should avoid pretending every provider has the same certainty. If model
listing fails but a provider commonly hides models, accept with a warning rather
than blocking the user.

## Runtime Integration

The viewer backend already has the right high-level boundary:

```text
AgentRuntimeClient.stream_chat(thread_id, messages, context_packet, tools, model_profile)
```

The next step is to resolve `model_profile` from `flow model` configuration
instead of only from environment variables.

Runtime flow:

1. Viewer chat receives a user message plus thread/context attachment refs.
2. Backend compacts thread context, selected/visible part facts, measurements,
   annotations, and validator evidence.
3. Model profile resolver selects active provider/model.
4. Provider runtime adapter maps the Flow CAD request to the provider transport.
5. Streamed provider output is normalized into Flow CAD events.
6. CAD-safe tool calls, if supported, route through Flow CAD services only.
7. Final assistant/tool events are persisted back into the design thread.

The provider layer owns authentication, base URL, model discovery, and transport
mapping. The design-thread layer owns CAD context, safe tools, persistence, and
source-mutation boundaries.

## Hermes Reuse Targets

High-value Hermes code to reuse or closely adapt:

- `hermes_cli/subcommands/model.py`: command shape and option names.
- `hermes_cli/models.py`: provider catalogs, live model discovery, cache policy,
  local model probing, provider-specific validation, and soft-accept behavior.
- `hermes_cli/providers.py`: canonical provider identity, aliases, overlays, and
  transport detection patterns.
- `providers/base.py`: declarative `ProviderProfile` shape.
- `providers/__init__.py`: provider registry and plugin discovery pattern.
- focused provider declarations for the scoped Tier 1/Tier 2 providers.
- `hermes_cli/auth.py`: provider auth config, OAuth/device flows, token refresh,
  token import, token-pool behavior, and local/no-auth placeholders.
- `hermes_cli/model_setup_flows.py`: provider-specific setup recipes.
- `hermes_cli/model_switch.py`: scriptable provider/model switching behavior.
- `hermes_cli/fallback_cmd.py`: fallback chain persistence and UX.
- `hermes_cli/config.py` and `utils.atomic_yaml_write`: atomic config writes,
  config recovery, and secrets/config separation.
- Hermes tests covering provider persistence, Codex auth, model validation
  fallback, setup delegation, and fallback providers.

Do not reuse directly:

- Hermes' full agent loop.
- Hermes' generic workspace `write_file` or shell tools.
- Hermes' global conversation model.
- The whole `hermes_cli.main` god-file as a dependency.
- Hermes-specific environment variable names as Flow CAD's primary API.

Flow CAD should copy the hard-earned provider logic that applies to the scoped
providers, but keep the workbench, viewer, CAD tools, and thread schemas native.

## Hermes Provider Sync Strategy

Future Hermes updates will probably add providers, repair provider quirks, and
adjust model discovery rules. Flow CAD should make relevant improvements easy to
pull in, but update-sync should stay secondary to a correct local implementation.

Preferred sync shape:

- Keep copied provider declarations close to Hermes' data shape where practical.
- Store provider-specific setup quirks in small strategy modules instead of
  scattering them through the viewer or chat code.
- Keep local Flow CAD extensions in separate fields such as CAD capability
  metadata, screenshot support, and CAD-safe tool support.
- Add a small comparison script later that can report scoped providers whose
  Hermes definitions changed.
- Record the Hermes source commit or date whenever substantial provider code is
  copied.

Do not block the first working provider broker on perfect automatic syncing or
full Hermes parity. Manual cherry-picking from Hermes is acceptable until the
provider layer proves stable.

## Implementation Plan

### PS-0: Codex Runtime Bridge Spike

Before building the full provider framework, prove the highest-priority provider
path: the user's existing Codex plan and local Codex install.

This spike does not replace the provider plan. It validates whether Flow CAD can
delegate design-thread chat to Codex without owning OpenAI/ChatGPT credentials.

Questions to answer:

- Can Flow CAD call the local Codex runtime/app-server/CLI in a structured way?
- Can Flow CAD rely on Codex' existing auth store instead of reading or storing
  OpenAI/ChatGPT credentials?
- Can Codex receive a compact CAD context packet and return a response suitable
  for design-thread chat?
- Can Flow CAD keep CAD mutation authority inside draft transactions, preview,
  focused validation, and explicit user acceptance?

Spike result on 2026-06-09:

- `codex` is installed locally and reports version `0.138.0`.
- `codex doctor` reports stored auth mode `chatgpt` with stored ChatGPT tokens
  and no stored API key in `~/.codex/auth.json`; Flow CAD does not need to own
  those credentials for a delegated Codex run.
- `codex app-server` exists, but the app-server path is still experimental and
  was not running during the spike.
- `codex exec --json --ephemeral --sandbox read-only` successfully accepted a
  CAD context packet and returned JSON suitable for a Flow CAD assistant message.
- `CodexExecAgentRuntimeClient` successfully called the local Codex CLI and
  returned normalized Flow CAD stream events: `assistant_delta` followed by
  `done`.
- The B3 viewer was started with `FLOW_CAD_AGENT_RUNTIME=codex`; both
  `/api/design-threads/{thread_id}/chat/stream` and the fallback
  `/api/design-threads/{thread_id}/chat` returned persisted assistant messages
  with `runtime: CodexExecAgentRuntimeClient` instead of the built-in
  `flow_cad_stub`.
- Nested sandbox execution failed before model invocation because Codex could
  not initialize its in-process app-server state on the read-only filesystem; the
  same command succeeded when run in the normal local environment.
- Some approval flags shown in `codex exec --help` were rejected by this
  installed CLI version, so the bridge should use the proven command shape rather
  than relying on help text alone.

Accepted first implementation:

- Add a narrow `CodexExecAgentRuntimeClient` behind the existing
  `AgentRuntimeClient` protocol.
- Select it with `FLOW_CAD_AGENT_RUNTIME=codex`.
- Shell out to `codex exec --json --ephemeral --sandbox read-only`.
- Pass only compact messages, compact CAD context, model profile metadata, and
  Flow CAD safe tool descriptions.
- Do not pass generic shell or filesystem mutation tools.
- Treat Codex output as assistant text unless/until a later provider framework
  adds structured tool-call handling.
- Keep CAD edits behind Flow CAD draft transaction, preview, focused validation,
  and explicit user acceptance.

Done means:

- Focused tests prove the Codex adapter builds the read-only/ephemeral command,
  filters unsafe tools from the prompt, parses the final Codex agent message, and
  reports nonzero Codex exits as structured runtime errors.
- The viewer backend can select the Codex adapter through environment
  configuration.
- A manual proof run confirms the installed Codex CLI can answer a CAD context
  packet using existing local Codex credentials.
- The streaming and non-streaming chat endpoints both persist Codex-backed
  assistant messages when the runtime is enabled.

If this bridge becomes brittle, continue with the native provider plan starting
with OpenAI API and local providers. If it remains stable, Codex becomes the
first concrete `AgentRuntimeClient` provider while the broader `flow model`
framework waits.

### PS-1: Provider Support Document And Scaffold

Add this plan, then scaffold the package and CLI group without real provider
auth. Include a fake provider and config store so tests can prove the command
shape, persistence, and status output.

Done means:

- `flow model status` works with no configured provider.
- `flow model use fake/test-model` persists a selected profile in a temp config
  during tests.
- Config writes are atomic and path-contained.

### PS-2: Port Provider Profile And Registry

Adapt Hermes' declarative provider profile and registry pattern. Start with a
small curated set, but keep aliases and provider metadata extensible.

Initial provider records:

- `openai`
- `openai-codex`
- `gemini`
- `llamastudio`
- `lmstudio`
- `local-openai-compatible`
- `openrouter`
- `anthropic-beta`

Done means:

- `flow model providers` lists Tier 1 providers by default.
- `flow model providers --all` includes beta providers.
- Alias resolution is tested.
- Provider records include support tier, transport, auth mode, capabilities, and
  validation status.

### PS-3: Local Providers First

Implement local provider setup and probing.

LlamaStudio:

- Treat it as a named provider, not just a URL.
- Reuse its streaming/profile/lifecycle ideas where they are cleanly separable.
- Add a health check that can tell the user whether the runtime is available.

LM Studio:

- Probe the default local OpenAI-compatible server.
- Fetch `/models` where available.
- Save the selected model and base URL.

Generic local endpoints:

- Support llama.cpp, vLLM, and custom OpenAI-compatible URLs through the
  `local-openai-compatible` provider.
- Accept manual model names when model discovery is unavailable, with warnings.

Done means:

- A local provider can be selected, tested, and used by the fake/design-thread
  streaming path.
- The user sees useful diagnostics when the local runtime is not running.

### PS-4: Hosted Providers

Port the provider flows that unlock the top hosted choices without taking on
Hermes-scale support.

Priority:

1. OpenAI API key flow.
2. OpenAI Codex account flow, if the Hermes code can be reused cleanly.
3. Gemini API key flow.
4. OpenRouter API key flow.
5. Anthropic API key flow as beta.

Done means:

- `flow model login <provider>` stores credentials outside the project.
- `flow model list <provider>` fetches live models or falls back with warnings.
- `flow model test` verifies each Tier 1 provider with a small prompt when
  credentials are available.
- Anthropic remains labeled beta unless a live validation path exists.

### PS-5: Viewer And Design-Thread Integration

Resolve the active profile in the viewer backend and expose it to the chat UI.

Backend:

- Replace env-only runtime selection with provider-profile resolution plus env
  override.
- Add `/api/model-profile` and `/api/model-profile/status`.
- Include provider/model/capability metadata in assistant messages.

Frontend:

- Show active provider/model in the Chat workspace.
- Warn when the selected model lacks image input or tool calling.
- Keep model setup in CLI first; add in-viewer switching later if needed.

Done means:

- A user can configure a provider with `flow model`, restart or reload the viewer,
  and see that provider used for design-thread chat.

### PS-6: Fallbacks, Doctor, And Import

Add operational polish after the first real providers work.

- Fallback chain: try another provider/model on rate limit, overload, or network
  failure.
- `flow model doctor`: check auth, endpoint health, model list, selected profile,
  and viewer runtime wiring.
- Optional `flow model import hermes`: read selected Hermes provider/model and
  offer to copy compatible settings without moving secrets blindly.

Done means provider setup failures are diagnosable without reading logs.

### PS-7: Optional Provider Expansion

Add more Hermes-supported providers only when there is clear user demand and a
validation path. Expansion is not a first-pass goal.

Done means adding a provider usually means adding a profile, auth strategy,
discovery strategy, capability metadata, and tests, not editing viewer chat code.

## Test Plan

Add focused Python tests for:

- config path resolution and atomic writes
- corrupt config backup/recovery
- secrets never written to project-local config
- provider registry alias resolution
- provider grouping, support tier, and current-provider display
- model profile persistence
- model cache read/write and refresh behavior
- fake provider `flow model test`
- local endpoint `/models` parsing
- manual custom endpoint acceptance with warning
- beta provider labeling
- auth-store read/write with safe permissions where supported
- viewer backend profile resolution with env override
- provider capability warnings in context packets or API status

When copying Hermes behavior, port the corresponding Hermes tests where possible
instead of trusting manual CLI checks.

## Completion Criteria

Provider support is complete for the first production slice when:

- `flow model` gives a Hermes-style provider selection experience.
- LlamaStudio and LM Studio are both first-class named local providers.
- OpenAI, Gemini, local OpenAI-compatible, and OpenRouter can be configured and
  tested when credentials/endpoints are available.
- Anthropic is either validated and promoted to Tier 1 or clearly labeled beta.
- A custom OpenAI-compatible endpoint can be configured and tested.
- The active provider/model is persisted outside the project source tree.
- The viewer backend resolves the active provider profile.
- Design-thread chat uses the selected runtime or reports why it cannot.
- Capability metadata tells the user whether screenshots, annotations, and
  CAD-safe tools will be sent as image input, text context, or not at all.
- Provider errors are surfaced as structured chat/runtime events instead of
  silent no-response failures.

# Model Provider Support Plan

Date: 2026-06-09

## Purpose

Flow CAD should let users connect the model provider that fits their workflow
instead of hard-coding one local runtime or one hosted account. The design-thread
chat surface should eventually feel like a normal model-backed CAD workspace:
pick a provider, authenticate or point at a local endpoint, choose a model, test
it, and then use it for viewport-aware chat with CAD-safe tools.

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

Use a Hermes Agent style model-provider broker rather than a one-off
LlamaStudio-only adapter.

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
allow it. The preferred approach is to copy or adapt focused modules into a small
Flow CAD provider subsystem, preserving upstream MIT attribution where source is
copied, rather than taking a large runtime dependency on all of Hermes.

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

## First-Class Providers

Flow CAD should not treat "local model" as one provider.

These should be first-class local/provider targets:

- `llamastudio`: the LlamaStudio application/runtime. This is a BLR-local
  runtime worth integrating as a named provider, not just an anonymous
  OpenAI-compatible URL.
- `lmstudio`: LM Studio, the desktop local-model app with a model server. It
  should be probed and configured as a named provider.
- `llama.cpp`: a standalone llama-server or compatible HTTP endpoint.
- `ollama`: local Ollama server and installed model list.
- `vllm`: OpenAI-compatible local or remote vLLM endpoint.
- `openai-compatible`: custom URL with optional API key.

These hosted/account providers should be planned as normal providers, not
special cases wired into chat:

- `openai-codex`: Codex/ChatGPT account style auth where available.
- `openai-api`: direct OpenAI API key.
- `anthropic`: direct Anthropic API and, where practical, Claude account-backed
  flows.
- `openrouter`: multi-model pay-per-use aggregator.
- `nous`: Nous Portal subscription/provider flow.
- `google-gemini`: direct Gemini API.
- `google-gemini-cli`: account/OAuth style Gemini Code Assist flow where
  practical.
- `xai` and `xai-oauth`: direct and account-backed Grok flows.
- `qwen`, `dashscope`, and Qwen OAuth style flows where practical.
- `deepseek`, `mistral`, `novita`, `bedrock`, `azure-foundry`, and other
  providers already represented in Hermes' provider catalog.

The first implementation does not need every provider fully working. It does
need the architecture to make adding a Hermes-supported provider mechanical.

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
    openai_compatible.py
    openai_codex.py
    openai_api.py
    anthropic.py
```

A provider profile should be declarative enough that adding a simple provider
does not require editing the chat runtime:

```text
ProviderProfile
  id
  display_name
  aliases
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
2. Group local providers, account/OAuth providers, direct API providers,
   aggregators, and custom endpoints.
3. Highlight first-class local options: LlamaStudio and LM Studio.
4. Prompt for only the credentials needed by the chosen provider.
5. Fetch or display model choices.
6. Save the active model profile.
7. Run an optional test prompt before returning success.

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
- `plugins/model-providers/*`: focused provider declarations.
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

Flow CAD should copy the hard-earned provider logic but keep the workbench,
viewer, CAD tools, and thread schemas native.

## Hermes Provider Sync Strategy

Future Hermes updates will probably add providers, repair provider quirks, and
adjust model discovery rules. Flow CAD should make those improvements easy to
pull in, but update-sync should stay secondary to a correct local implementation.

Preferred sync shape:

- Keep copied provider declarations close to Hermes' data shape where practical.
- Store provider-specific setup quirks in small strategy modules instead of
  scattering them through the viewer or chat code.
- Keep local Flow CAD extensions in separate fields such as CAD capability
  metadata, screenshot support, and CAD-safe tool support.
- Add a small comparison script later that can report providers present in
  Hermes but missing from Flow CAD.
- Record the Hermes source commit or date whenever substantial provider code is
  copied.

Do not block the first working provider broker on perfect automatic syncing.
Manual cherry-picking from Hermes is acceptable until the provider layer proves
stable.

## Implementation Plan

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

- `llamastudio`
- `lmstudio`
- `llama.cpp`
- `ollama`
- `openai-compatible`
- `openai-codex`
- `openai-api`
- `anthropic`
- `openrouter`
- `nous`
- `google-gemini`
- `custom`

Done means:

- `flow model providers` lists grouped providers.
- Alias resolution is tested.
- Provider records include transport, auth mode, and capabilities.

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

- Support llama.cpp, vLLM, Ollama, and custom OpenAI-compatible URLs.
- Accept manual model names when model discovery is unavailable, with warnings.

Done means:

- A local provider can be selected, tested, and used by the fake/design-thread
  streaming path.
- The user sees useful diagnostics when the local runtime is not running.

### PS-4: Hosted And Account Providers

Port the provider flows that unlock broad user choice.

Priority:

1. OpenAI Codex account flow.
2. OpenAI API key flow.
3. Anthropic API key flow.
4. OpenRouter API key flow.
5. Nous Portal flow.
6. Google/Gemini direct and account-backed flows where practical.

Done means:

- `flow model login <provider>` stores credentials outside the project.
- `flow model list <provider>` fetches live models or falls back with warnings.
- `flow model test` verifies the selected provider with a small prompt.

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

### PS-7: Provider Parity Expansion

Add more Hermes-supported providers as mechanical follow-up work. Provider parity
is not complete until adding a provider usually means adding a profile, auth
strategy, discovery strategy, and tests, not editing the viewer chat code.

## Test Plan

Add focused Python tests for:

- config path resolution and atomic writes
- corrupt config backup/recovery
- secrets never written to project-local config
- provider registry alias resolution
- provider grouping and current-provider display
- model profile persistence
- model cache read/write and refresh behavior
- fake provider `flow model test`
- local endpoint `/models` parsing
- manual custom endpoint acceptance with warning
- auth-store read/write with safe permissions where supported
- viewer backend profile resolution with env override
- provider capability warnings in context packets or API status

When copying Hermes behavior, port the corresponding Hermes tests where possible
instead of trusting manual CLI checks.

## Completion Criteria

Provider support is complete for the first production slice when:

- `flow model` gives a Hermes-style provider selection experience.
- LlamaStudio and LM Studio are both first-class named local providers.
- At least one account-backed provider and one direct API-key provider work.
- A custom OpenAI-compatible endpoint can be configured and tested.
- The active provider/model is persisted outside the project source tree.
- The viewer backend resolves the active provider profile.
- Design-thread chat uses the selected runtime or reports why it cannot.
- Capability metadata tells the user whether screenshots, annotations, and
  CAD-safe tools will be sent as image input, text context, or not at all.
- Provider errors are surfaced as structured chat/runtime events instead of
  silent no-response failures.

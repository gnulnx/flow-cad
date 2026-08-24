# Production Release Gate

`flow release gate` is the strict-manifest production check. It is deliberately
separate from `flow cad build --part ...`: ordinary part review stays scoped and
does not wait for project tests, every active export, or expensive project
checks.

## Contract

The command submits a durable `release-gate` job to the same project-local job
service used by workbench build commands. The CLI prints phase, progress, and
elapsed-time events while it follows the job. `Ctrl-C` requests cancellation;
project imports, CAD builds, hooks, tests, and Git checks run in killable child
processes so the runtime can enforce cancellation and timeouts.

The gate checks, in order:

1. Strict manifest/schema and SQLite registry/assembly integrity.
2. The downstream SDK ownership boundary and importability of the project
   parameter provider, every active generator, and every release hook. Project
   source may import only `flow_cad.sdk` and the explicitly public,
   geometry-heavy `flow_cad.geometry` helper facade.
3. Fresh STEP plus declared optional STL output for every `active` part through
   the same isolated, deterministic scoped-build worker used by public part
   builds.
4. Registry and viewer hashes against the bytes actually published under
   `exports/`.
5. A complete SHA-256 manifest for the fresh active STEP/STL set.
6. Registered project hooks, followed by the project test suite.
7. The 15-second scoped-part hard threshold, 120-second whole-gate target, and
   180-second whole-gate hard timeout.
8. A clean Git worktree.

The gate never publishes into `migration/` and never edits the versioned
manifest. Migration source and artifact baselines remain immutable authorities.

## Project-owned hooks

Hooks are declared in `flowcad.project.yaml` and must resolve inside the
manifest's `python_package`:

```yaml
release_hooks:
  - key: focused
    kind: validator
    provider: my_project.validators.release:validate_focused
    timeout_seconds: 20
  - key: assembly_clearance
    kind: interference
    provider: my_project.validators.release:validate_interference
    timeout_seconds: 45
  - key: print_manifest
    kind: print_manifest
    provider: my_project.validators.release:validate_print_manifest
    timeout_seconds: 20
```

Project code imports only public hook contracts from `flow_cad.sdk`. A hook
receives `ReleaseHookContext`, including the project root and fresh artifact
identities, and returns `ReleaseHookResult`, a Boolean, or a mapping containing
`ok`. Hook failures and timeouts are recorded against the exact
`hook:<kind>:<key>` phase. Missing interference or print-manifest hooks are
reported as `skipped/not_registered`; they are not silently inferred by the
runtime.

```python
from flow_cad.sdk import ReleaseHookContext, ReleaseHookResult


def validate_focused(context: ReleaseHookContext) -> ReleaseHookResult:
    return ReleaseHookResult(
        ok=bool(context.artifacts),
        summary="fresh artifact set is available",
        details={"artifact_count": len(context.artifacts)},
    )
```

## Outputs and commands

The current machine-readable timing/profile report is
`.flow/release/latest.json`. The checksum file is
`.flow/release/artifact-manifest.sha256`. Both are disposable runtime state;
the report includes every phase duration, hook result, artifact SHA-256 and byte
count, viewer revision, thresholds, terminal status, and failed phase when
applicable.

Exact developer commands:

```bash
# Fast release contracts, without real CAD subprocess exports
.venv/bin/python -m pytest tests/foundation/test_manifest.py tests/foundation/test_sdk_contract.py tests/release/test_release_gate.py -m "not integration"

# Focused release suite, including bounded real STEP/STL publication
.venv/bin/python -m pytest tests/foundation/test_manifest.py tests/foundation/test_sdk_contract.py tests/release/test_release_gate.py

# Project production release gate
flow release gate --request-id <stable-request-id>
```

The workbench backend exposes the same immediate command at
`POST /api/workbench/v1/release/gate` with `{"request_id":"..."}`. Query,
stream, and cancel it through the standard `/api/workbench/v1/jobs/...`
endpoints.

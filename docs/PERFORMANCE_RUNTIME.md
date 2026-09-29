# Performance controls and verification

The viewer keeps completed display downloads and decoded geometry across part
visibility changes. Byte storage has a 128 MiB LRU budget. Decoded geometry has
a 256 MiB budget for unused resources; displayed geometry holds leases and can
exceed that budget until hidden. Geometry is disposed only after its last lease
is released and it is evicted. Cache identity includes the API, source revision
and scene contract version. Failed conversions remain retryable.

Bounding boxes are combined without copying all component vertex buffers into
an extra merged mesh. Parsed GLB geometry is reused; shared GLTF instances receive
independent transforms. Scene fitting completes when restored geometry is ready.

## CAD execution

Build generation/export, display conversion and exact-topology extraction share
a persistent spawned-process pool. Geometry never crosses the process boundary.
The API and list/query paths remain free of CAD imports. Generated files are
staged in disposable directories; the parent checks cancellation before publishing
artifacts, indexes or feature/display caches. Same-part builds serialize before
claiming a worker. Project builds use a bounded parallel window, retaining manifest
result order and monotonic aggregate progress.

Selected builds and exact measurements overtake queued background jobs. Selected
display requests get the same job-queue priority. Running native calls are not
preempted for priority, but cancellation kills their worker and releases its slot.
Failed, crashed, timed-out and memory-exceeding workers are discarded. Revisions
of transitive project Python and package assets invalidate warm workers, including
same-size, same-mtime Python edits. Workers also recycle after a task limit.

User defaults and project overrides use the existing typed config mechanism:

```toml
[cad]
workers = 2
native_threads = 1
memory_mb = 2048
timeout_seconds = 600
recycle_after_tasks = 32
```

Each worker receives explicit CPU affinity and native-library thread settings.
On Linux, RSS is checked every 50 ms while working; address space also has an
OS limit allowing virtual reservations above the RSS threshold. This is not a
cgroup hard RSS cap. Project-local file locks share active worker slots with
concurrent API/CLI runners using the same configuration. Idle processes may retain
CAD caches until recycling or shutdown. The defaults bound CAD worker memory to
roughly 4 GiB, excluding the API, browser and transient allocation between checks.

A successful build also prepares a GLB directly from the generated shape. It
avoids reimporting STEP just to display the result. Preview colors follow the
source hierarchy; some STEP exporter roundtrips lose moved assembly styles.
Exact topology and measurements still use the indexed STEP artifact. Preview
failure is reported independently of successful STEP/STL generation.

## Reproducing measurements

Use the same inputs, CPU affinity, memory limits and browser/render backend for
comparisons. Run heavy benchmarks separately from full product regression suites.
Existing display caches should stay intact: cold browser opening and cold kernel
conversion measure different paths.

```sh
python scripts/benchmark_display.py \
  --frontend http://127.0.0.1:<frontend-port> \
  --api http://127.0.0.1:<backend-port> \
  --part <part-key> --assembly-parts <count> --output /tmp/display.json

python scripts/benchmark_cad.py \
  --project <project-root> --part <part-key> \
  --scene <part-key> --scene <another-part-key> --output /tmp/cad.json
```

The browser benchmark requires Playwright Chromium, uses SwiftShader, and exercises
Show fully assembled, which clears the current preview. The CAD benchmark reads
original artifacts and stages all generated outputs under `.flow/benchmarks`.
It compares fresh serial scene processes with cold/warm two-worker conversion,
and reports cold/warm builds including preview generation. A warm result is not
evidence of an improvement over an unmeasured warm baseline.

Tests cover bounded reuse/eviction, revision changes, cancellation, actual worker
reuse and parallel overlap, shared process slots, same-part serialization, crash
recovery, source invalidation, priority, preview placement/colors and STEP authority.
Product geometry equivalence and served-pixel review belong in the downstream
project's validation report.

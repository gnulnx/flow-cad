import { afterEach, describe, expect, it, vi } from 'vitest'
import { createHttpWorkbenchClient } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('workbench HTTP adapter', () => {
  it('maps metadata-first STEP authority and the content-addressed STL display separately', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toBe('/api/parts')
      return jsonResponse({
        project_id: 'flow_b2',
        python_package: 'flow_b2',
        manifest_schema_version: 1,
        manifest_sha256: 'manifest-sha',
        revision: 4,
        part_count: 1,
        occurrence_count: 1,
        parts: [{
          uuid: 'guard-uuid',
          key: 'unitree_l2_arch_guard',
          aliases: ['arch_guard'],
          role: 'printable',
          status: 'active',
          artifacts: [
            { kind: 'step', sha256: 'step-sha', state: 'indexed' },
            { kind: 'stl', sha256: 'stl-sha', state: 'indexed' },
          ],
          occurrences: [{ id: 'guard-main' }],
          geometry_authority: 'step_kernel',
          quality_label: 'exact',
          capabilities: { exact_topology: true, mesh_only: false },
          warnings: [],
          artifact_revision: 'step-sha',
          display_revision: 'stl-sha',
          model_url: '/api/models/stl-sha',
        }],
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const snapshot = await createHttpWorkbenchClient().getInventory()
    expect(snapshot.parts[0]).toMatchObject({
      geometryAuthority: 'step',
      qualityLabel: 'Exact',
      occurrenceIds: ['guard-main'],
      authorityHash: 'step-sha',
      displayArtifact: {
        contentHash: 'stl-sha',
        url: '/api/models/stl-sha',
      },
    })
  })

  it('uses durable chat endpoints and translates CAD context into the append-only contract', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe('/api/chat/threads/default/turns')
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>
      expect(body).toMatchObject({
        request_id: 'request-1',
        content: 'Inspect this guard',
        context: {
          selected_part_uuid: 'guard-uuid',
          visible_occurrence_ids: ['guard-main'],
          artifact_hashes: { 'guard-uuid': 'stl-sha' },
          viewer_revision: '4',
        },
      })
      return jsonResponse({
        turn_id: 'turn-1',
        provider_status: 'awaiting_dispatch',
        events: [{ event_id: 'assistant-event', turn_id: 'turn-1', event_type: 'assistant_created', payload: {} }],
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const message = await createHttpWorkbenchClient().sendTurn({
      requestId: 'request-1',
      threadId: 'default',
      content: 'Inspect this guard',
      context: {
        projectRevision: 4,
        selectedPartUuid: 'guard-uuid',
        selectedPartKey: 'unitree_l2_arch_guard',
        visibleOccurrenceIds: ['guard-main'],
        artifactHashes: { 'guard-uuid': 'stl-sha' },
      },
    })

    expect(message).toMatchObject({ id: 'assistant-event', turnId: 'turn-1', state: 'streaming' })
  })

  it('maps durable succeeded jobs to the completed UI state', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      jobs: [{
        job_id: 'job-1',
        kind: 'exact-topology',
        state: 'succeeded',
        phase: 'complete',
        progress: 1,
        message: 'Complete',
        elapsed_seconds: 0.2,
        updated_at: '2026-08-22T00:00:00Z',
        cancellation_requested: false,
        payload: { label: 'Exact topology' },
      }],
    }))
    vi.stubGlobal('fetch', fetchMock)

    const jobs = await createHttpWorkbenchClient('').getJobs()

    expect(jobs[0]).toMatchObject({ id: 'job-1', label: 'Exact topology', state: 'complete' })
  })
})

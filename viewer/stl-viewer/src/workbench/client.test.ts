import { afterEach, describe, expect, it, vi } from 'vitest'
import { createHttpWorkbenchClient } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
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
          occurrences: [{
            assembly_key: 'active',
            id: 'guard-main',
            translation_mm: [1, 2, 3],
            rotation_deg: [0, 90, 0],
          }],
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
    expect(snapshot.activeAssemblyId).toBe('active')
    expect(snapshot.parts[0]).toMatchObject({
      geometryAuthority: 'step',
      qualityLabel: 'Exact',
      occurrenceIds: ['guard-main'],
      occurrences: [{
        assemblyId: 'active',
        id: 'guard-main',
        translationMm: [1, 2, 3],
        rotationDeg: [0, 90, 0],
      }],
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

  it('keeps exact STEP extraction as an explicit cold job followed by a warm revision result', async () => {
    const revision = 'a'.repeat(64)
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        status: 'job_required',
        part_uuid: 'part-1',
        artifact_revision: revision,
        geometry_authority: 'step_kernel',
        quality: 'exact',
      }, 202))
      .mockResolvedValueOnce(jsonResponse({
        status: 'queued',
        part_uuid: 'part-1',
        artifact_revision: revision,
        job: { job_id: 'job-1' },
        result_url: `/api/parts/part-1/exact-features?artifact_revision=${revision}`,
      }, 202))
      .mockResolvedValueOnce(jsonResponse({
        status: 'ready',
        part_uuid: 'part-1',
        artifact_revision: revision,
        geometry_authority: 'step_kernel',
        quality: 'exact',
        units: 'mm',
        cache_hit: true,
        warnings: [],
        features: [{
          id: 'line_edge:0',
          kind: 'line_edge',
          source: 'step_topology',
          quality: 'exact',
          start_mm: [0, 0, 0],
          end_mm: [10, 0, 0],
          midpoint_mm: [5, 0, 0],
          length_mm: 10,
        }],
      }))
    vi.stubGlobal('fetch', fetchMock)
    const client = createHttpWorkbenchClient()

    expect(await client.getExactFeatures('part-1', revision)).toMatchObject({ status: 'job_required' })
    expect(await client.queueExactFeatures('part-1', revision, 'request-1')).toMatchObject({
      status: 'queued',
      jobId: 'job-1',
    })
    expect(await client.getExactFeatures('part-1', revision)).toMatchObject({
      status: 'ready',
      artifactRevision: revision,
      cacheHit: true,
      features: [{
        kind: 'line_edge',
        startMm: [0, 0, 0],
        endMm: [10, 0, 0],
        lengthMm: 10,
      }],
    })
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ request_id: 'request-1', artifact_revision: revision }),
    })
  })

  it('loads and saves revision-bound measurement snapshots through the durable API', async () => {
    const revision = 'a'.repeat(64)
    const measurement = {
      measurementId: 'measurement-1',
      kind: 'distance' as const,
      title: 'Two vertices',
      quality: 'exact' as const,
      startMm: [0, 0, 0] as [number, number, number],
      endMm: [3, 4, 0] as [number, number, number],
      totalMm: 5,
      deltaMm: [3, 4, 0] as [number, number, number],
      featureIds: ['vertex-1', 'vertex-2'],
      hidden: false,
      pinned: true,
      labelOffsetPx: [8, -2] as [number, number],
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        snapshot: {
          thread_id: 'thread-1',
          part_uuid: 'part-1',
          artifact_revision: revision,
          measurements: [{
            measurement_id: measurement.measurementId,
            kind: measurement.kind,
            title: measurement.title,
            quality: measurement.quality,
            start_mm: measurement.startMm,
            end_mm: measurement.endMm,
            total_mm: measurement.totalMm,
            delta_mm: measurement.deltaMm,
            feature_ids: measurement.featureIds,
            hidden: measurement.hidden,
            pinned: measurement.pinned,
            label_offset_px: measurement.labelOffsetPx,
          }],
        },
      }))
      .mockResolvedValueOnce(jsonResponse({ created: true }, 201))
    vi.stubGlobal('fetch', fetchMock)
    const client = createHttpWorkbenchClient()

    await expect(client.getLatestMeasurementSnapshot('thread-1', 'part-1')).resolves.toEqual({
      threadId: 'thread-1',
      partUuid: 'part-1',
      artifactRevision: revision,
      measurements: [measurement],
    })
    await client.saveMeasurementSnapshot({
      requestId: 'save-1',
      threadId: 'thread-1',
      partUuid: 'part-1',
      artifactRevision: revision,
      measurements: [measurement],
    })

    expect(String(fetchMock.mock.calls[1][0])).toContain('/api/measurements/threads/thread-1/parts/part-1/snapshots')
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({
        request_id: 'save-1',
        artifact_revision: revision,
        measurements: [{
          measurement_id: measurement.measurementId,
          kind: measurement.kind,
          title: measurement.title,
          quality: measurement.quality,
          start_mm: measurement.startMm,
          end_mm: measurement.endMm,
          total_mm: measurement.totalMm,
          delta_mm: measurement.deltaMm,
          feature_ids: measurement.featureIds,
          hidden: measurement.hidden,
          pinned: measurement.pinned,
          label_offset_px: measurement.labelOffsetPx,
        }],
      }),
    })
  })
})

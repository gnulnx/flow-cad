import { afterEach, describe, expect, it, vi } from 'vitest'
import { saveAnnotationSnapshot } from './client'

afterEach(() => vi.restoreAllMocks())

describe('annotation API client', () => {
  it('binds normalized review marks to thread, camera, artifact, and visible occurrences', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      created: true,
      event: {
        sequence: 1,
        event_id: 'event-1',
        thread_id: 'thread-1',
        event_type: 'annotation_snapshot_saved',
        snapshot: {},
      },
    }), { status: 201, headers: { 'Content-Type': 'application/json' } }))

    await saveAnnotationSnapshot('http://127.0.0.1:8000/', {
      requestId: 'save-1',
      threadId: 'thread-1',
      hidden: false,
      marks: [{
        id: 'arrow-1',
        kind: 'arrow',
        points: [[0.1, 0.2], [0.7, 0.8]],
        color: '#79cbd1',
        strokeWidth: 2,
        intent: 'review_intent',
      }],
      context: {
        camera: { position: [1, 2, 3], target: [0, 0, 0] },
        viewport: { width: 1280, height: 720, render_context: 'viewport-canvas' },
        artifactRevision: 'step-sha',
        visibleOccurrenceIds: ['guard-main'],
        viewerRevision: '7',
      },
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://127.0.0.1:8000/api/annotations/threads/thread-1/snapshots')
    const body = JSON.parse(String(init?.body))
    expect(body).toMatchObject({
      request_id: 'save-1',
      marks: [{ mark_id: 'arrow-1', intent: 'review_intent', points: [[0.1, 0.2], [0.7, 0.8]] }],
      context: {
        artifact_revision: 'step-sha',
        visible_occurrence_ids: ['guard-main'],
        viewer_revision: '7',
      },
    })
  })
})

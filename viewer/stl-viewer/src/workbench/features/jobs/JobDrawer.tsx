import { useEffect, useState } from 'react'
import type { WorkbenchClient, WorkbenchJob } from '../../contracts'

interface JobDrawerProps {
  client: WorkbenchClient
}

export function JobDrawer({ client }: JobDrawerProps) {
  const [jobs, setJobs] = useState<WorkbenchJob[] | null>(null)
  const [error, setError] = useState(false)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    client.getJobs(controller.signal).then((nextJobs) => {
      setJobs(nextJobs)
      setError(false)
    }).catch(() => {
      if (!controller.signal.aborted) setError(true)
    })
    return () => controller.abort()
  }, [client])

  const activeJobs = jobs?.filter((job) => job.state === 'queued' || job.state === 'running') ?? []
  return (
    <section className={`job-drawer ${expanded ? 'job-drawer--expanded' : ''}`} aria-label="Task activity">
      <button type="button" className="job-drawer__summary" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
        <span className={`health-dot ${activeJobs.length > 0 ? 'health-dot--working' : error ? 'health-dot--error' : 'health-dot--ready'}`} />
        <strong>{activeJobs.length > 0 ? `${activeJobs.length} active task${activeJobs.length === 1 ? '' : 's'}` : error ? 'Task service unavailable' : 'No active tasks'}</strong>
        <span>{activeJobs[0]?.phase ?? 'Builds and conversions appear here'}</span>
        <span aria-hidden="true">{expanded ? '⌄' : '⌃'}</span>
      </button>
      {expanded ? (
        <div className="job-list">
          {jobs && jobs.length > 0 ? jobs.map((job) => (
            <article key={job.id} className="job-row">
              <div><strong>{job.label}</strong><span>{job.phase} · {(job.elapsedMs / 1000).toFixed(1)}s</span></div>
              <progress value={job.progress ?? undefined} max={1} />
              <span>{job.state}</span>
              {job.cancellable && (job.state === 'queued' || job.state === 'running')
                ? <button type="button" onClick={() => void client.cancelJob(job.id)}>Cancel</button>
                : null}
            </article>
          )) : <p>{error ? 'The optional task endpoint is not connected yet.' : 'Completed and active jobs will be listed here.'}</p>}
        </div>
      ) : null}
    </section>
  )
}

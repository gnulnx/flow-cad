import { useState } from 'react'
import type { WorkbenchPart } from '../../contracts'

export function PartFileActions({ part, onOpen }: { part: WorkbenchPart; onOpen?: () => void }) {
  const [copyStatus, setCopyStatus] = useState('')
  const [downloadStatus, setDownloadStatus] = useState('')
  const [downloading, setDownloading] = useState(false)
  const copyName = async () => {
    try {
      await navigator.clipboard.writeText(part.key)
      setCopyStatus('Part name copied')
    } catch {
      setCopyStatus('Could not copy. Select the part name above to copy it.')
    }
  }
  const download = async (artifact: NonNullable<WorkbenchPart['downloads']>[number]) => {
    if (downloading) return
    setDownloading(true)
    setDownloadStatus(`Downloading ${artifact.kind.toUpperCase()}…`)
    try {
      const response = await fetch(artifact.url)
      if (!response.ok) throw new Error(`Download failed (${response.status}). Refresh the part and retry.`)
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url; link.download = artifact.filename
      document.body.appendChild(link); link.click(); link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setDownloadStatus(`${artifact.kind.toUpperCase()} download started`)
    } catch (error) {
      setDownloadStatus(error instanceof Error ? error.message : String(error))
    } finally { setDownloading(false) }
  }
  return <div className="part-file-actions" aria-label="Selected part files">
    <strong>{part.displayName ?? part.key}</strong>
    <code>{part.key}</code>
    <div className="inspection-toolbar">
      <button type="button" className="tool-button" onClick={() => void copyName()}>Copy part name</button>
      {onOpen ? <button type="button" className="tool-button" onClick={onOpen}>Open part</button> : null}
      {part.downloads?.map((artifact) => <a key={artifact.kind} className="tool-button"
        href={artifact.url} download={artifact.filename} aria-disabled={downloading}
        onClick={(event) => { event.preventDefault(); void download(artifact) }}>Download {artifact.kind.toUpperCase()}</a>)}
    </div>
    {copyStatus ? <small role="status">{copyStatus}</small> : null}
    {downloadStatus ? <small role="status">{downloadStatus}</small> : null}
    {!part.downloads?.length ? <small>No built STEP or STL is available for this part.</small> : null}
  </div>
}

import { useState } from 'react'
import type { WorkbenchPart } from '../../contracts'

export function PartFileActions({ part, onOpen }: { part: WorkbenchPart; onOpen?: () => void }) {
  const [copyStatus, setCopyStatus] = useState('')
  const copyName = async () => {
    try {
      await navigator.clipboard.writeText(part.key)
      setCopyStatus('Part name copied')
    } catch {
      setCopyStatus('Could not copy. Select the part name above to copy it.')
    }
  }
  return <div className="part-file-actions" aria-label="Selected part files">
    <strong>{part.displayName ?? part.key}</strong>
    <code>{part.key}</code>
    <div className="inspection-toolbar">
      <button type="button" className="tool-button" onClick={() => void copyName()}>Copy part name</button>
      {onOpen ? <button type="button" className="tool-button" onClick={onOpen}>Open part</button> : null}
      {part.downloads?.map((artifact) => <a key={artifact.kind} className="tool-button"
        href={artifact.url} download={artifact.filename}>Download {artifact.kind.toUpperCase()}</a>)}
    </div>
    {copyStatus ? <small role="status">{copyStatus}</small> : null}
    {!part.downloads?.length ? <small>No built STEP or STL is available for this part.</small> : null}
  </div>
}

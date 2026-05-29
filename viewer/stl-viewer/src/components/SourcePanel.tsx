import type { ReactNode } from 'react'
import type { SourceContext } from '../types'

interface SourcePanelProps {
  context: SourceContext | null
  activeId: string | null
  collapsed: boolean
  onToggle: () => void
}

const PYTHON_KEYWORDS = new Set([
  'and',
  'as',
  'assert',
  'break',
  'class',
  'continue',
  'def',
  'elif',
  'else',
  'except',
  'False',
  'finally',
  'for',
  'from',
  'if',
  'import',
  'in',
  'is',
  'lambda',
  'None',
  'not',
  'or',
  'pass',
  'raise',
  'return',
  'True',
  'try',
  'while',
  'with',
  'yield',
])

const PYTHON_BUILTINS = new Set([
  'abs',
  'bool',
  'dict',
  'enumerate',
  'float',
  'int',
  'len',
  'list',
  'max',
  'min',
  'range',
  'round',
  'set',
  'str',
  'tuple',
])

function sourceLineParts(line: string) {
  const match = line.match(/^(\s*\d+:\s?)(.*)$/)
  return match ? { prefix: match[1], code: match[2] } : { prefix: '', code: line }
}

interface SourceLine {
  lineNumber: number | null
  code: string
}

function sourceLines(context: SourceContext): SourceLine[] {
  if (context.content !== undefined) {
    const content = context.content.endsWith('\n') ? context.content.slice(0, -1) : context.content
    return content.split('\n').map((code, index) => ({
      lineNumber: index + 1,
      code,
    }))
  }

  return context.excerpt.split('\n').map((line) => {
    const { prefix, code } = sourceLineParts(line)
    const lineNumber = Number(prefix.replace(':', '').trim())
    return {
      lineNumber: Number.isFinite(lineNumber) ? lineNumber : null,
      code,
    }
  })
}

function isHighlighted(context: SourceContext, lineNumber: number | null) {
  return (
    lineNumber !== null
    && context.highlight_start_line !== undefined
    && context.highlight_end_line !== undefined
    && lineNumber >= context.highlight_start_line
    && lineNumber <= context.highlight_end_line
  )
}

function tokenClass(token: string) {
  if (PYTHON_KEYWORDS.has(token)) return 'syntax-keyword'
  if (PYTHON_BUILTINS.has(token)) return 'syntax-builtin'
  if (/^@[A-Za-z_]\w*$/.test(token)) return 'syntax-decorator'
  if (/^\d+(?:\.\d+)?$/.test(token)) return 'syntax-number'
  if (/^#/.test(token)) return 'syntax-comment'
  if (/^['"]/.test(token)) return 'syntax-string'
  return null
}

function highlightPython(code: string) {
  const tokenPattern = /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|#[^\n]*|@[A-Za-z_]\w*|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b)/g
  const nodes: ReactNode[] = []
  let lastIndex = 0

  for (const match of code.matchAll(tokenPattern)) {
    const token = match[0]
    const index = match.index ?? 0
    if (index > lastIndex) nodes.push(code.slice(lastIndex, index))

    const className = tokenClass(token)
    nodes.push(className ? <span key={`${index}-${token}`} className={className}>{token}</span> : token)
    lastIndex = index + token.length
  }

  if (lastIndex < code.length) nodes.push(code.slice(lastIndex))
  return nodes
}

function HighlightedSource({ context }: { context: SourceContext }) {
  const lines = sourceLines(context)

  return (
    <pre className="source-code">
      {lines.map((line, index) => {
        const className = isHighlighted(context, line.lineNumber)
          ? 'source-line source-line-highlight'
          : 'source-line'
        return (
          <code key={index} className={className}>
            <span className="source-line-number">{line.lineNumber ?? ''}</span>
            <span className="source-line-code">{highlightPython(line.code)}</span>
          </code>
        )
      })}
    </pre>
  )
}

export default function SourcePanel({ context, activeId, collapsed, onToggle }: SourcePanelProps) {
  return (
    <div className={`source-panel ${collapsed ? 'panel-collapsed' : ''}`}>
      <button type="button" className="panel-title panel-toggle" onClick={onToggle}>Source</button>
      {collapsed ? null : (
        context ? (
          <>
            <div className="source-file">{context.relative_file_path}</div>
            <HighlightedSource context={context} />
          </>
        ) : (
          <div className="source-empty">{activeId ?? 'No part selected'}</div>
        )
      )}
    </div>
  )
}

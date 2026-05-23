import type { ModelData } from '../types'

interface ModelListProps {
  models: ModelData[]
  activeName: string | null
  onActivate: (name: string | null) => void
}

const formatMm = (value: number) => `${value.toFixed(value >= 100 ? 1 : 2)} mm`

export default function ModelList({ models, activeName, onActivate }: ModelListProps) {
  if (models.length === 0) return null

  return (
    <div style={{
      position: 'absolute',
      top: '70px',
      left: '32px',
      zIndex: 2,
      background: 'rgba(22,33,62,0.95)',
      padding: '10px 16px',
      borderRadius: '8px',
      border: '1px solid #0f3460',
      maxHeight: '60vh',
      overflowY: 'auto',
      minWidth: '250px',
    }}>
      <h3 style={{ fontSize: '12px', color: '#e94560', marginBottom: '8px' }}>Loaded Parts</h3>
      <ul style={{ listStyle: 'none' }}>
        {models.map((model) => (
          <li
            key={model.name}
            onClick={() => onActivate(model.name)}
            style={{
              padding: '4px 8px',
              fontSize: '12px',
              cursor: 'pointer',
              borderRadius: '4px',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              background: model.name === activeName ? 'rgba(233,69,96,0.25)' : 'transparent',
              color: model.name === activeName ? '#e94560' : '#e0e0e0',
            }}
          >
            <div style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{model.name}</div>
            {model.name === activeName ? (
              <div style={{ color: '#b8c1cc', fontSize: '11px', marginTop: '4px', lineHeight: 1.4 }}>
                X {formatMm(model.bounds.size.x)}<br />
                Y {formatMm(model.bounds.size.y)}<br />
                Z {formatMm(model.bounds.size.z)}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

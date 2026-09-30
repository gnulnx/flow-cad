import { useCallback, useEffect, useMemo, useState } from 'react'
import { componentHidden, emptyInspection, inspectComponents, type InspectionAction, type SceneComponent } from './componentInspection'

export function useComponentInspection(components: SceneComponent[], scope: string) {
  const [stored, setStored] = useState({ scope, state: emptyInspection })
  // Scope includes requested artifacts/occurrences, not arrival order or focus.
  const state = stored.scope === scope ? stored.state : emptyInspection
  useEffect(() => {
    setStored((current) => current.scope === scope ? current : { scope, state: emptyInspection })
  }, [scope])
  const dispatch = useCallback((action: InspectionAction) => {
    setStored((current) => ({ scope, state: inspectComponents(current.scope === scope ? current.state : emptyInspection, action) }))
  }, [scope])
  const hiddenKeys = useMemo(() => new Set(components.filter((component) => componentHidden(state, component.key)).map((component) => component.key)), [components, state])
  const selected = components.find((component) => component.key === state.selected) ?? null
  const select = useCallback((key: string | null) => dispatch({ type: 'select', key }), [dispatch])
  return { state, dispatch, hiddenKeys, selected, select }
}

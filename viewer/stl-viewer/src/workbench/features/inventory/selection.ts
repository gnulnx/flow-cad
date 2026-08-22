export type PartSelectionMode = 'focus' | 'replace' | 'toggle'

export interface PartSelectionState {
  activePartUuid: string | null
  explicitVisiblePartUuids: string[] | null
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values)]
}

export function applyPartSelection(
  state: PartSelectionState,
  partUuid: string,
  mode: PartSelectionMode,
  defaultVisiblePartUuids: readonly string[],
): PartSelectionState {
  if (mode === 'focus') return { ...state, activePartUuid: partUuid }

  const visible = unique(state.explicitVisiblePartUuids ?? defaultVisiblePartUuids)
  if (mode === 'replace') {
    const isOnlyVisiblePart = visible.length === 1 && visible[0] === partUuid
    return isOnlyVisiblePart
      ? { activePartUuid: null, explicitVisiblePartUuids: [] }
      : { activePartUuid: partUuid, explicitVisiblePartUuids: [partUuid] }
  }

  if (!visible.includes(partUuid)) {
    return {
      activePartUuid: partUuid,
      explicitVisiblePartUuids: [...visible, partUuid],
    }
  }

  const remaining = visible.filter((uuid) => uuid !== partUuid)
  const activePartUuid = state.activePartUuid && state.activePartUuid !== partUuid && remaining.includes(state.activePartUuid)
    ? state.activePartUuid
    : remaining[remaining.length - 1] ?? null
  return { activePartUuid, explicitVisiblePartUuids: remaining }
}

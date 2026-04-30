import { useQueries } from '@tanstack/react-query'
import { getAgentProfile } from '../api/client'

/** Resolves a list of agent IDs to { agentId -> name } map. Falls back to shortId. */
export function useAgentNames(agentIds: string[]): Record<string, string> {
  const unique = [...new Set(agentIds)].filter(Boolean)
  const results = useQueries({
    queries: unique.map((id) => ({
      queryKey: ['agent-profile', id],
      queryFn: () => getAgentProfile(id),
      staleTime: 5 * 60 * 1000,
    })),
  })
  const map: Record<string, string> = {}
  unique.forEach((id, i) => {
    const data = results[i]?.data
    map[id] = data?.name ?? (id.slice(0, 8) + '…')
  })
  return map
}

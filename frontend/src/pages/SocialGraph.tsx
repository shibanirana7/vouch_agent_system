import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getTrustNetwork, createTrust, updateTrust, deleteTrust, getFriendReviews, searchUsers, getConnectionRequests, respondToConnectionRequest, getSentRequests, TrustRelationship } from '../api/client'
import { useAuthStore } from '../store/auth'
import { useAgentNames } from '../hooks/useAgentNames'

const LEVEL_LABELS = {
  close_friend: 'Close Friend',
  friend: 'Friend',
  acquaintance: 'Acquaintance',
}

const LEVEL_COLORS = {
  close_friend: 'bg-blush-50 text-blush-600 border-blush-200',
  friend: 'bg-mauve-50 text-mauve-600 border-mauve-200',
  acquaintance: 'bg-gray-100 text-gray-500 border-gray-200',
}


export default function SocialGraph() {
  const agentId = useAuthStore((s) => s.agentId)!
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [showAdd, setShowAdd] = useState(false)
  const [newAgentId, setNewAgentId] = useState('')
  const [newLevel, setNewLevel] = useState<'close_friend' | 'friend' | 'acquaintance'>('friend')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ name: string; agent_id: string }[]>([])
  const [searching, setSearching] = useState(false)

  async function handleSearch() {
    if (!searchQuery.trim()) return
    setSearching(true)
    try {
      const results = await searchUsers(searchQuery.trim())
      setSearchResults(results.filter((r) => r.agent_id !== agentId))
    } finally {
      setSearching(false)
    }
  }

  const { data: connections = [], isLoading } = useQuery({
    queryKey: ['trust', agentId],
    queryFn: () => getTrustNetwork(agentId),
  })

  const { data: connectionRequests = [] } = useQuery({
    queryKey: ['connection-requests', agentId],
    queryFn: () => getConnectionRequests(agentId),
    refetchInterval: 30000,
  })

  const { data: sentRequests = [] } = useQuery({
    queryKey: ['sent-requests', agentId],
    queryFn: () => getSentRequests(agentId),
    refetchInterval: 30000,
  })

  const [respondingId, setRespondingId] = useState<string | null>(null)
  const [acceptLevel, setAcceptLevel] = useState<Record<string, string>>({})

  const respondMutation = useMutation({
    mutationFn: ({ requestId, action, trustLevel }: { requestId: string; action: 'accept' | 'deny'; trustLevel?: string }) =>
      respondToConnectionRequest(requestId, action, trustLevel),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connection-requests', agentId] })
      qc.invalidateQueries({ queryKey: ['trust', agentId] })
      setRespondingId(null)
    },
  })

  const declineAllMutation = useMutation({
    mutationFn: () => Promise.all(connectionRequests.map((r) => respondToConnectionRequest(r.id, 'deny'))),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connection-requests', agentId] })
    },
  })

  const { data: friendReviews = [] } = useQuery({
    queryKey: ['friend-reviews', agentId],
    queryFn: () => getFriendReviews(agentId),
    enabled: connections.length > 0,
  })

  const allAgentIds = [
    ...connections.map((c) => c.to_agent_id),
    ...friendReviews.map((r) => r.agent_id),
  ]
  const agentNames = useAgentNames(allAgentIds)

  const addMutation = useMutation({
    mutationFn: () => createTrust(agentId, newAgentId, newLevel),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trust', agentId] })
      setShowAdd(false)
      setNewAgentId('')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ toId, level }: { toId: string; level: string }) =>
      updateTrust(agentId, toId, level),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trust', agentId] })
      setEditingId(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (toId: string) => deleteTrust(agentId, toId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['trust', agentId] }),
  })

  if (isLoading)
    return (
      <div className="text-center py-16 text-gray-400 text-sm uppercase tracking-widest">
        Loading…
      </div>
    )

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">My Trust Network</h1>
          <p className="text-xs text-gray-400 uppercase tracking-widest font-medium mt-0.5">
            Your agent weights recommendations by trust level
          </p>
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="px-5 py-2.5 bg-blush-500 hover:bg-blush-600 text-white text-xs font-semibold rounded-full transition-all shadow-pink hover:shadow-pink-lg uppercase tracking-widest whitespace-nowrap"
        >
          + Add connection
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="bg-white border border-gray-100 rounded-2xl p-6 mb-6 shadow-sm">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">
            Add a trusted connection
          </h2>

          {/* Username search */}
          <div className="flex gap-2 mb-3">
            <input
              placeholder="Search by username…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
            />
            <button
              onClick={handleSearch}
              disabled={searching || !searchQuery.trim()}
              className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
            >
              {searching ? '…' : 'Search'}
            </button>
          </div>

          {/* Username search results */}
          {searchResults.length > 0 && (
            <div className="mb-3 border border-gray-100 rounded-xl overflow-hidden">
              {searchResults.map((r) => (
                <button
                  key={r.agent_id}
                  onClick={() => { setNewAgentId(r.agent_id); setSearchResults([]); setSearchQuery(r.name) }}
                  className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-blush-50 transition-colors text-left border-b border-gray-50 last:border-0"
                >
                  <span className="text-sm font-medium text-gray-800">{r.name}</span>
                  <span className="text-[11px] text-gray-400 font-mono">{r.agent_id.slice(0, 8)}…</span>
                </button>
              ))}
            </div>
          )}
          {searchResults.length === 0 && searchQuery && !searching && (
            <p className="text-xs text-gray-400 mb-3">No users found. You can also paste an Agent ID directly below.</p>
          )}

          {/* Direct agent ID + trust level + add */}
          <div className="flex gap-3 flex-wrap">
            <input
              placeholder="Agent ID"
              value={newAgentId}
              onChange={(e) => setNewAgentId(e.target.value)}
              className="flex-1 min-w-40 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
            />
            <select
              value={newLevel}
              onChange={(e) => setNewLevel(e.target.value as typeof newLevel)}
              className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
            >
              <option value="close_friend">Close Friend (0.9)</option>
              <option value="friend">Friend (0.6)</option>
              <option value="acquaintance">Acquaintance (0.3)</option>
            </select>
            <button
              onClick={() => addMutation.mutate()}
              disabled={!newAgentId || addMutation.isPending}
              className="px-5 py-2.5 bg-blush-500 hover:bg-blush-600 disabled:opacity-40 text-white text-xs font-semibold rounded-full transition-all shadow-pink uppercase tracking-widest"
            >
              Add
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-3">
            Share your Agent ID with friends:{' '}
            <code className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded-lg font-mono text-[11px]">
              {agentId}
            </code>
          </p>
        </div>
      )}

      {/* Pending connection requests */}
      {connectionRequests.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500">
              Connection Requests
              <span className="ml-2 inline-flex items-center justify-center w-5 h-5 rounded-full bg-blush-500 text-white text-[10px] font-bold">
                {connectionRequests.length}
              </span>
            </h2>
            <button
              onClick={() => declineAllMutation.mutate()}
              disabled={declineAllMutation.isPending}
              className="text-xs text-gray-400 hover:text-red-500 disabled:opacity-40 transition-colors"
            >
              {declineAllMutation.isPending ? 'Declining…' : 'Decline all'}
            </button>
          </div>
          <div className="grid gap-3">
            {connectionRequests.map((req) => (
              <div key={req.id} className="bg-white border border-blush-100 rounded-2xl p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-800">{req.from_name}</p>
                    {req.message && (
                      <p className="text-xs text-gray-500 mt-0.5 italic">"{req.message}"</p>
                    )}
                    {req.similarity_score != null && (
                      <p className="text-[11px] text-gray-400 mt-1">
                        {Math.round(req.similarity_score * 100)}% taste match
                      </p>
                    )}
                  </div>

                  {respondingId === req.id ? (
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <select
                        value={acceptLevel[req.id] ?? 'acquaintance'}
                        onChange={(e) => setAcceptLevel((prev) => ({ ...prev, [req.id]: e.target.value }))}
                        className="text-xs border border-gray-200 rounded-xl px-3 py-1.5 focus:outline-none bg-gray-50"
                      >
                        <option value="close_friend">Close Friend</option>
                        <option value="friend">Friend</option>
                        <option value="acquaintance">Acquaintance</option>
                      </select>
                      <button
                        onClick={() => respondMutation.mutate({ requestId: req.id, action: 'accept', trustLevel: acceptLevel[req.id] ?? 'acquaintance' })}
                        disabled={respondMutation.isPending}
                        className="px-4 py-1.5 bg-blush-500 hover:bg-blush-600 disabled:opacity-40 text-white text-xs font-semibold rounded-full transition-all"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => setRespondingId(null)}
                        className="text-xs text-gray-400 hover:text-gray-600"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <button
                        onClick={() => setRespondingId(req.id)}
                        className="px-4 py-1.5 bg-blush-500 hover:bg-blush-600 text-white text-xs font-semibold rounded-full transition-all shadow-pink"
                      >
                        Accept
                      </button>
                      <button
                        onClick={() => respondMutation.mutate({ requestId: req.id, action: 'deny' })}
                        disabled={respondMutation.isPending}
                        className="px-4 py-1.5 text-xs font-semibold text-gray-400 hover:text-red-500 rounded-full hover:bg-red-50 transition-all"
                      >
                        Deny
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sent (outgoing) requests — pending */}
      {sentRequests.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-3">
            Sent Requests
            <span className="ml-2 text-gray-400 font-normal normal-case">waiting for a response</span>
          </h2>
          <div className="grid gap-3">
            {sentRequests.map((req) => (
              <div key={req.id} className="bg-white border border-gray-100 rounded-2xl p-4 shadow-sm flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-700">{req.to_name}</p>
                  {req.similarity_score != null && (
                    <p className="text-[11px] text-gray-400 mt-0.5">
                      {Math.round(req.similarity_score * 100)}% taste match
                    </p>
                  )}
                </div>
                <span className="flex-shrink-0 text-[11px] font-semibold uppercase tracking-widest text-gray-400 bg-gray-50 border border-gray-100 px-3 py-1 rounded-full">
                  Pending
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {connections.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <div className="text-5xl mb-4">🤝</div>
          <p className="text-sm font-medium">No connections yet.</p>
          <p className="text-xs mt-1 text-gray-300 max-w-xs mx-auto">
            Add people you trust and their reviews will influence your agent&apos;s recommendations.
          </p>
        </div>
      ) : (
        <div className="grid gap-3">
          {connections.map((c) => (
            <ConnectionCard
              key={c.id}
              connection={c}
              name={agentNames[c.to_agent_id]}
              isEditing={editingId === c.id}
              onEdit={() => setEditingId(c.id)}
              onCancelEdit={() => setEditingId(null)}
              onUpdate={(level) => updateMutation.mutate({ toId: c.to_agent_id, level })}
              onDelete={() => deleteMutation.mutate(c.to_agent_id)}
              onViewProfile={() => navigate(`/social/profile/${c.to_agent_id}`)}
              updating={updateMutation.isPending}
              deleting={deleteMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* Friends' Reviews feed */}
      {friendReviews.length > 0 && (
        <section className="mt-10 border-t border-gray-100 pt-8">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">
            Friends' Reviews
          </h2>
          <div className="grid gap-3">
            {friendReviews.map((r, i) => (
              <div key={i} className="bg-white border border-gray-100 rounded-2xl p-4 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-gray-800 text-sm">{r.product}</p>
                    <p className="text-[11px] text-gray-400 mt-0.5 truncate">
                      {agentNames[r.agent_id]}
                    </p>
                  </div>
                  <p className="text-[11px] text-gray-400 mt-0.5 flex-shrink-0 capitalize">{r.category}</p>
                </div>
                <p className="mt-2 text-xs text-gray-500 italic leading-relaxed border-t border-gray-50 pt-2">
                  "{r.text.replace(/^\[.*?\]\s*[^:]+:\s*/, '').replace(/\s*\(rating:.*\)$/, '')}"
                </p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function ConnectionCard({
  connection, name, isEditing, onEdit, onCancelEdit, onUpdate, onDelete, onViewProfile, updating, deleting
}: {
  connection: TrustRelationship
  name: string
  isEditing: boolean
  onEdit: () => void
  onCancelEdit: () => void
  onUpdate: (level: string) => void
  onDelete: () => void
  onViewProfile: () => void
  updating: boolean
  deleting: boolean
}) {
  const [selectedLevel, setSelectedLevel] = useState(connection.trust_level)
  const weight = connection.trust_weight
  const percent = Math.round(weight * 100)

  return (
    <div className="bg-white border border-gray-100 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          {/* Trust weight ring */}
          <div className="flex-shrink-0 relative w-12 h-12">
            <svg className="w-12 h-12 -rotate-90" viewBox="0 0 48 48">
              <circle cx="24" cy="24" r="20" fill="none" stroke="#f3f4f6" strokeWidth="4" />
              <circle
                cx="24" cy="24" r="20"
                fill="none"
                stroke="#ff0066"
                strokeWidth="4"
                strokeLinecap="round"
                strokeDasharray={`${2 * Math.PI * 20}`}
                strokeDashoffset={`${2 * Math.PI * 20 * (1 - weight)}`}
                opacity="0.8"
                style={{ transition: 'stroke-dashoffset 0.8s ease' }}
              />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-[11px] font-bold text-blush-500">
              {percent}
            </span>
          </div>

          <div className="min-w-0">
            <div className="text-sm font-semibold text-gray-800 truncate max-w-[200px]">
              {name}
            </div>
            <span
              className={`text-xs px-2.5 py-0.5 mt-1 inline-block rounded-full border font-semibold ${
                LEVEL_COLORS[connection.trust_level as keyof typeof LEVEL_COLORS] ?? 'bg-gray-100 text-gray-500 border-gray-200'
              }`}
            >
              {LEVEL_LABELS[connection.trust_level as keyof typeof LEVEL_LABELS] ?? connection.trust_level}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isEditing ? (
            <>
              <select
                value={selectedLevel}
                onChange={(e) => setSelectedLevel(e.target.value as 'close_friend' | 'friend' | 'acquaintance')}
                className="text-xs border border-gray-200 rounded-xl px-3 py-1.5 focus:outline-none bg-gray-50"
              >
                <option value="close_friend">Close Friend</option>
                <option value="friend">Friend</option>
                <option value="acquaintance">Acquaintance</option>
              </select>
              <button
                onClick={() => onUpdate(selectedLevel)}
                disabled={updating}
                className="px-4 py-1.5 bg-blush-500 hover:bg-blush-600 disabled:opacity-40 text-white text-xs font-semibold rounded-full transition-all"
              >
                Save
              </button>
              <button
                onClick={onCancelEdit}
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={onViewProfile}
                className="text-xs font-semibold text-gray-400 hover:text-blush-500 px-3 py-1.5 rounded-full hover:bg-blush-50 transition-all"
              >
                Profile
              </button>
              <button
                onClick={onEdit}
                className="text-xs font-semibold text-gray-400 hover:text-blush-500 px-3 py-1.5 rounded-full hover:bg-blush-50 transition-all"
              >
                Edit
              </button>
              <button
                onClick={onDelete}
                disabled={deleting}
                className="text-xs font-semibold text-gray-300 hover:text-red-500 disabled:opacity-40 px-3 py-1.5 rounded-full hover:bg-red-50 transition-all"
              >
                Remove
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPreferences, getAgent, setAutonomous } from '../api/client'
import { useAuthStore } from '../store/auth'
import { useChatStore } from '../store/chat'

export default function Profile() {
  const { agentId, userName } = useAuthStore()
  const clearMessages = useChatStore((s) => s.clearMessages)
  const [cleared, setCleared] = useState(false)

  function handleClearChat() {
    clearMessages()
    setCleared(true)
    setTimeout(() => setCleared(false), 2000)
  }

  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['preferences', agentId],
    queryFn: () => getPreferences(agentId!),
    enabled: !!agentId,
  })

  const { data: agentData } = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => getAgent(agentId!),
    enabled: !!agentId,
  })

  const autonomousMutation = useMutation({
    mutationFn: (enabled: boolean) => setAutonomous(agentId!, enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agent', agentId] }),
  })

  const initials = userName?.slice(0, 2).toUpperCase() ?? '??'

  return (
    <div className="max-w-2xl">
      {/* Profile header */}
      <div className="flex items-center gap-5 mb-10">
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center text-lg font-bold text-white flex-shrink-0 shadow-pink"
          style={{ background: 'linear-gradient(135deg, #ff4da0 0%, #ff0066 100%)' }}
        >
          {initials}
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">{userName}</h1>
          <p className="text-[11px] text-gray-400 font-mono mt-0.5 select-all">
            ID: {agentId}
          </p>
        </div>
      </div>

      {/* Preferences section */}
      <section>
        <div className="flex items-baseline gap-3 mb-4">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500">
            Your taste profile
          </h2>
          {data?.preferences.length ? (
            <span className="text-xs text-blush-500 font-semibold">
              {data.preferences.length} preferences
            </span>
          ) : null}
        </div>

        {isLoading ? (
          <p className="text-gray-400 text-sm">Loading…</p>
        ) : !data?.preferences.length ? (
          <div className="bg-white border border-gray-100 rounded-2xl p-6 text-gray-400 text-sm shadow-sm">
            <span className="text-2xl block mb-2">✦</span>
            No preferences recorded yet.{' '}
            <span className="text-gray-500 font-medium">
              Chat with your agent and tell it what you like!
            </span>
          </div>
        ) : (
          <ul className="space-y-2">
            {data.preferences.map((pref, i) => (
              <li
                key={i}
                className="bg-white border border-gray-100 rounded-2xl px-5 py-3.5 text-sm text-gray-700 flex items-start gap-3 shadow-sm hover:shadow-md transition-shadow"
              >
                <span className="text-blush-400 mt-0.5 flex-shrink-0 font-bold">✦</span>
                <span>{pref}</span>
              </li>
            ))}
          </ul>
        )}

        <p className="text-xs text-gray-400 mt-4 leading-relaxed">
          These preferences are learned from your conversations and purchase history — not things
          you explicitly stated.
        </p>
      </section>

      {/* Autonomous agent */}
      <section className="mt-10 border-t border-gray-100 pt-8">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">
          Autonomous agent
        </h2>
        <div className="bg-white border border-gray-100 rounded-2xl px-5 py-4 shadow-sm flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-gray-800">Run in the background</p>
            <p className="text-xs text-gray-400 mt-1 leading-relaxed max-w-sm">
              When enabled, your agent proactively refills your wishlist and discovers new friends
              with similar taste — without you needing to ask.
            </p>
          </div>
          <button
            onClick={() => autonomousMutation.mutate(!agentData?.is_autonomous)}
            disabled={autonomousMutation.isPending || agentData === undefined}
            className={`relative flex-shrink-0 w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-blush-400 disabled:opacity-50 ${
              agentData?.is_autonomous ? 'bg-blush-500' : 'bg-gray-200'
            }`}
            role="switch"
            aria-checked={agentData?.is_autonomous ?? false}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200 ${
                agentData?.is_autonomous ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2 leading-relaxed">
          {agentData?.is_autonomous
            ? 'Your agent is active. It runs on every scheduler tick.'
            : 'Your agent is paused and will not run autonomously.'}
        </p>
      </section>

      {/* Chat history */}
      <section className="mt-10 border-t border-gray-100 pt-8">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">
          Chat history
        </h2>
        <button
          onClick={handleClearChat}
          className="px-4 py-2 text-sm rounded-xl border border-red-200 text-red-500 hover:bg-red-50 transition-colors"
        >
          {cleared ? 'Cleared!' : 'Clear chat history'}
        </button>
        <p className="text-xs text-gray-400 mt-2">
          Removes all messages from your local chat view. Does not affect your preferences or purchase history.
        </p>
      </section>
    </div>
  )
}

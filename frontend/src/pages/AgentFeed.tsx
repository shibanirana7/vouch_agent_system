import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getConsultations, getTrustNetwork, consultAgent, Consultation } from '../api/client'
import { useAuthStore } from '../store/auth'
import { useAgentNames } from '../hooks/useAgentNames'
import { JsonBlock } from '../components/JsonBlock'

function agentColor(id: string) {
  const hue = (id.charCodeAt(0) * 37 + id.charCodeAt(1) * 17) % 360
  return `hsl(${hue},65%,52%)`
}

function Avatar({ id, size = 32 }: { id: string; size?: number }) {
  return (
    <div
      className="rounded-full flex items-center justify-center font-bold text-white flex-shrink-0 text-xs"
      style={{ width: size, height: size, background: agentColor(id) }}
    >
      {id.slice(0, 2).toUpperCase()}
    </div>
  )
}


function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/** Group consultations by the other agent, sorted by most recent message. */
function groupByAgent(consultations: Consultation[], myId: string) {
  const map = new Map<string, Consultation[]>()
  for (const c of consultations) {
    const other = c.from_agent_id === myId ? c.to_agent_id : c.from_agent_id
    if (!map.has(other)) map.set(other, [])
    map.get(other)!.push(c)
  }
  // Sort messages within each thread chronologically
  for (const thread of map.values()) {
    thread.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  }
  // Sort threads by most recent message
  return [...map.entries()].sort(
    (a, b) =>
      new Date(b[1][b[1].length - 1]!.created_at).getTime() -
      new Date(a[1][a[1].length - 1]!.created_at).getTime()
  )
}

export default function AgentFeed() {
  const agentId = useAuthStore((s) => s.agentId)!
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [activeThread, setActiveThread] = useState<string | null>(null)
  const [consultQuery, setConsultQuery] = useState('')
  const [consultTarget, setConsultTarget] = useState('')
  const [showConsult, setShowConsult] = useState(false)
  const [showA2A, setShowA2A] = useState(false)

  const { data: consultations = [], isLoading } = useQuery({
    queryKey: ['consultations', agentId],
    queryFn: () => getConsultations(agentId),
    refetchInterval: 10000,
  })

  const { data: connections = [] } = useQuery({
    queryKey: ['trust', agentId],
    queryFn: () => getTrustNetwork(agentId),
  })

  const consultMutation = useMutation({
    mutationFn: () => consultAgent(agentId, consultTarget, consultQuery),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['consultations', agentId] })
      setConsultQuery('')
      setActiveThread(data.to_agent_id)
      setShowConsult(false)
    },
  })

  const threads = groupByAgent(consultations, agentId)
  const selected = activeThread ?? (threads[0]?.[0] ?? null)
  const selectedThread = threads.find(([id]) => id === selected)?.[1] ?? []

  const allIds = [
    ...threads.map(([id]) => id),
    ...connections.map((c) => c.to_agent_id),
  ]
  const agentNames = useAgentNames(allIds)

  return (
    <div className="flex gap-0 bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden" style={{ height: 'calc(100vh - 120px)', minHeight: 480 }}>

      {/* Sidebar — thread list */}
      <div className="w-64 flex-shrink-0 border-r border-gray-100 flex flex-col">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-widest text-gray-500">Conversations</span>
          <button
            onClick={() => setShowConsult(true)}
            className="w-6 h-6 rounded-full bg-blush-500 text-white text-lg leading-none flex items-center justify-center hover:bg-blush-600 transition-colors flex-shrink-0"
            title="New conversation"
          >+</button>
        </div>

        {isLoading ? (
          <div className="flex-1 flex items-center justify-center text-xs text-gray-300">Loading…</div>
        ) : threads.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-gray-300">
            <div className="text-3xl mb-2">💬</div>
            <p className="text-xs">No conversations yet</p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            {threads.map(([otherId, msgs]) => {
              const last = msgs[msgs.length - 1]!
              const iAsked = last.from_agent_id === agentId
              const preview = iAsked ? last.query : last.response
              const isActive = (activeThread ?? threads[0]?.[0]) === otherId
              return (
                <button
                  key={otherId}
                  onClick={() => setActiveThread(otherId)}
                  className={`w-full flex items-start gap-3 px-4 py-3 text-left transition-colors border-b border-gray-50 ${isActive ? 'bg-blush-50' : 'hover:bg-gray-50'}`}
                >
                  <Avatar id={otherId} size={36} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-1">
                      <span className="text-xs font-semibold text-gray-700 truncate">{agentNames[otherId]}</span>
                      <span className="text-[10px] text-gray-300 flex-shrink-0">{timeAgo(last.created_at)}</span>
                    </div>
                    <p className="text-[11px] text-gray-400 truncate mt-0.5">{preview}</p>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Main — thread view */}
      <div className="flex-1 flex flex-col min-w-0">
        {showConsult ? (
          /* New conversation form */
          <div className="flex-1 flex flex-col">
            <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-3">
              <button onClick={() => setShowConsult(false)} className="text-gray-300 hover:text-gray-500 text-lg leading-none">←</button>
              <span className="text-sm font-semibold text-gray-700">Ask a trusted agent</span>
            </div>
            <div className="flex-1 p-5 flex flex-col gap-3">
              <select
                value={consultTarget}
                onChange={(e) => setConsultTarget(e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
              >
                <option value="">Select a trusted agent…</option>
                {connections.map((c) => (
                  <option key={c.to_agent_id} value={c.to_agent_id}>
                    {agentNames[c.to_agent_id]} — {c.trust_level.replace('_', ' ')}
                  </option>
                ))}
              </select>
              <textarea
                rows={4}
                placeholder="What do you want to ask? e.g. 'What moisturiser would you recommend for oily skin?'"
                value={consultQuery}
                onChange={(e) => setConsultQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && consultTarget && consultQuery.trim()) { e.preventDefault(); consultMutation.mutate() } }}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50 resize-none"
              />
              <button
                onClick={() => consultMutation.mutate()}
                disabled={!consultTarget || !consultQuery.trim() || consultMutation.isPending}
                className="self-end px-6 py-2.5 bg-blush-500 hover:bg-blush-600 disabled:opacity-40 text-white text-xs font-semibold rounded-full transition-all shadow-pink uppercase tracking-widest"
              >
                {consultMutation.isPending ? 'Asking…' : 'Send'}
              </button>
            </div>
          </div>
        ) : selected === null ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-300">
            <div className="text-4xl mb-3">💬</div>
            <p className="text-sm">Select a conversation or start a new one</p>
          </div>
        ) : (
          <>
            {/* Thread header */}
            <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-3">
              <Avatar id={selected} size={32} />
              <div>
                <p className="text-xs font-semibold text-gray-700">{agentNames[selected]}</p>
                <p className="text-[10px] text-gray-400">{selectedThread.length} message{selectedThread.length !== 1 ? 's' : ''}</p>
              </div>
              <div className="ml-auto flex items-center gap-3">
                <button
                  onClick={() => setShowA2A((v) => !v)}
                  className={`text-[10px] font-semibold uppercase tracking-widest px-3 py-1 rounded-full border transition-all ${
                    showA2A
                      ? 'bg-gray-900 text-green-400 border-gray-700'
                      : 'text-gray-400 border-gray-200 hover:border-gray-300 hover:text-gray-600'
                  }`}
                >
                  A2A
                </button>
                <button
                  onClick={() => navigate(`/social/profile/${selected}`)}
                  className="text-[10px] text-blush-400 hover:text-blush-600 font-semibold uppercase tracking-widest"
                >
                  Profile →
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-1">
              {selectedThread.map((c, i) => {
                const iAsked = c.from_agent_id === agentId
                const prevC = selectedThread[i - 1]
                const showDate = !prevC || new Date(c.created_at).toDateString() !== new Date(prevC.created_at).toDateString()
                return (
                  <div key={c.id}>
                    {showDate && (
                      <div className="text-center text-[10px] text-gray-300 my-3">
                        {new Date(c.created_at).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                      </div>
                    )}
                    {/* Query */}
                    <div className={`flex items-end gap-2 mb-1 ${iAsked ? 'flex-row-reverse' : 'flex-row'}`}>
                      {!iAsked && <Avatar id={c.from_agent_id} size={24} />}
                      <div className={`max-w-[72%] px-3.5 py-2 rounded-2xl text-sm ${
                        iAsked ? 'bg-blush-500 text-white rounded-br-sm' : 'bg-gray-100 text-gray-800 rounded-bl-sm'
                      }`}>
                        {c.query}
                      </div>
                    </div>
                    {/* Response */}
                    <div className={`flex items-end gap-2 ${iAsked ? 'flex-row' : 'flex-row-reverse'}`}>
                      {iAsked && <Avatar id={c.to_agent_id} size={24} />}
                      <div className={`max-w-[72%] px-3.5 py-2 rounded-2xl text-sm leading-relaxed ${
                        iAsked ? 'bg-gray-100 text-gray-700 rounded-bl-sm' : 'bg-blush-500 text-white rounded-br-sm'
                      }`}>
                        {c.response}
                      </div>
                    </div>
                    {/* A2A protocol envelopes */}
                    {showA2A && (c.a2a_request || c.a2a_response) && (
                      <div className="ml-8 mb-3 mt-1 space-y-1">
                        {c.a2a_request && (
                          <JsonBlock label="→ A2A request" data={c.a2a_request} />
                        )}
                        {c.a2a_response && (
                          <JsonBlock label="← A2A response" data={c.a2a_response} />
                        )}
                      </div>
                    )}
                    {showA2A && !c.a2a_request && (
                      <p className="ml-8 mb-3 text-[10px] text-gray-300 font-mono">no A2A envelope — pre-dates protocol upgrade</p>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Reply bar */}
            <ReplyBar
              disabled={consultMutation.isPending}
              onSend={(q) => {
                setConsultTarget(selected)
                setConsultQuery(q)
                consultMutation.mutate()
              }}
              pending={consultMutation.isPending}
            />
          </>
        )}
      </div>
    </div>
  )
}

function ReplyBar({ onSend, disabled, pending }: { onSend: (q: string) => void; disabled: boolean; pending: boolean }) {
  const [text, setText] = useState('')
  function submit() {
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText('')
  }
  return (
    <div className="px-4 py-3 border-t border-gray-100 flex items-end gap-2">
      <textarea
        rows={1}
        placeholder="Ask something…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
        className="flex-1 px-4 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50 resize-none"
      />
      <button
        onClick={submit}
        disabled={!text.trim() || disabled}
        className="px-4 py-2 bg-blush-500 hover:bg-blush-600 disabled:opacity-40 text-white text-xs font-semibold rounded-xl transition-all"
      >
        {pending ? '…' : '↑'}
      </button>
    </div>
  )
}

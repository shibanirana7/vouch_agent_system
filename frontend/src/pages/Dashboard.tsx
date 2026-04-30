import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  chatWithAgent, getNotifications, dismissNotification,
  addWishlistItem, respondToConnectionRequest,
  type AgentNotification,
} from '../api/client'
import { useAuthStore } from '../store/auth'
import { useChatStore } from '../store/chat'

/** Render a single line with inline **bold** and _italic_ markdown. */
function InlineMd({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_)/g)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**'))
          return <strong key={i}>{part.slice(2, -2)}</strong>
        if (part.startsWith('_') && part.endsWith('_'))
          return <em key={i}>{part.slice(1, -1)}</em>
        return <span key={i}>{part}</span>
      })}
    </>
  )
}

function MessageBody({ content }: { content: string }) {
  const lines = content.split('\n')
  const nodes: React.ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (/^[-*]\s/.test(line)) {
      const bullets: string[] = []
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        bullets.push(lines[i].replace(/^[-*]\s/, ''))
        i++
      }
      nodes.push(
        <ul key={i} className="list-disc list-inside space-y-0.5 my-1">
          {bullets.map((b, j) => <li key={j}><InlineMd text={b} /></li>)}
        </ul>
      )
    } else if (line.trim() === '') {
      nodes.push(<div key={i} className="h-2" />)
      i++
    } else {
      nodes.push(<p key={i}><InlineMd text={line} /></p>)
      i++
    }
  }
  return <div className="space-y-0.5">{nodes}</div>
}

function NotifCTA({ n, agentId, onDone }: { n: AgentNotification; agentId: string; onDone: () => void }) {
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)

  if (!n.action_type || done) return null

  async function handleAction() {
    setLoading(true)
    try {
      if (n.action_type === 'add_to_wishlist' && n.action_payload) {
        const p = n.action_payload as { product_name: string; description: string; is_recurring: boolean }
        await addWishlistItem(agentId, { product_name: p.product_name, description: p.description, is_recurring: p.is_recurring })
      } else if (n.action_type === 'add_friend' && n.action_payload) {
        const p = n.action_payload as { connection_request_id: string }
        await respondToConnectionRequest(p.connection_request_id, 'accept')
      }
      setDone(true)
      onDone()
    } catch {
      // no-op — user can dismiss manually
    } finally {
      setLoading(false)
    }
  }

  const label = n.action_type === 'add_to_wishlist' ? 'Add to Wishlist' : 'Accept'

  return (
    <button
      onClick={handleAction}
      disabled={loading}
      className="mt-1.5 px-2.5 py-1 bg-blush-500 hover:bg-blush-600 disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-colors"
    >
      {loading ? '…' : label}
    </button>
  )
}

function TypingDots() {
  return (
    <div className="flex gap-1.5 items-center py-1">
      {[0, 1, 2].map((i) => (
        <span key={i} className="w-2 h-2 rounded-full bg-blush-400 animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }} />
      ))}
    </div>
  )
}

export default function Dashboard() {
  const agentId = useAuthStore((s) => s.agentId)!
  const userName = useAuthStore((s) => s.userName)
  const { messages, isLoading, addMessage, setLoading } = useChatStore()
  const [input, setInput] = useState('')
  const [summaryDismissed, setSummaryDismissed] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const qc = useQueryClient()
  const { data: notifications = [] } = useQuery({
    queryKey: ['notifications', agentId],
    queryFn: () => getNotifications(agentId),
    refetchInterval: 60_000,
  })
  const dismissMutation = useMutation({
    mutationFn: (notifId: string) => dismissNotification(agentId, notifId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications', agentId] }),
  })

  const agentNotifications = notifications.filter(
    (n) => n.type !== 'connection_request' && n.type !== 'friend_review'
  )
  const restocks = agentNotifications.filter((n) => n.type === 'restock_due').length
  const showSummary = !summaryDismissed && restocks > 0

  const summaryParts: string[] = []
  if (restocks > 0) summaryParts.push(`added ${restocks} item${restocks > 1 ? 's' : ''} to your wishlist`)

  useEffect(() => {
    if (useChatStore.getState().messages.length === 0) {
      addMessage({
        role: 'assistant',
        content: `Hi ${userName}! I'm your personal beauty shopping agent. I know your preferences and can check what your trusted friends recommend. Ask me anything — what to buy, what looks good together, or just tell me about products you love or hate.`,
      })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send() {
    if (!input.trim() || isLoading) return
    const text = input.trim()
    setInput('')
    addMessage({ role: 'user', content: text })
    setLoading(true)
    try {
      const res = await chatWithAgent(agentId, text, messages.slice(-10))
      addMessage({ role: 'assistant', content: res.response })
    } catch {
      addMessage({ role: 'assistant', content: 'Sorry, something went wrong. Please try again.' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* While-you-were-away summary */}
      {showSummary && (
        <div className="mb-3 flex items-center justify-between gap-3 bg-gray-50 border border-gray-200 rounded-2xl px-4 py-2.5">
          <p className="text-xs text-gray-600">
            <span className="font-semibold text-gray-800">While you were away</span>
            {' — '}your agent {summaryParts.join(' and ')}.
          </p>
          <button
            onClick={() => setSummaryDismissed(true)}
            className="text-gray-400 hover:text-gray-600 text-xs flex-shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Persistent notifications */}
      {agentNotifications.length > 0 && (
        <div className="mb-3 space-y-2">
          {agentNotifications.map((n) => (
            <div key={n.id} className="flex items-start justify-between gap-3 bg-blush-50 border border-blush-200 rounded-2xl px-4 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="text-blush-700 font-semibold text-xs">{n.title}</p>
                <p className="text-blush-600 text-xs mt-0.5 leading-relaxed">{n.body}</p>
                <NotifCTA n={n} agentId={agentId} onDone={() => dismissMutation.mutate(n.id)} />
              </div>
              <button
                onClick={() => dismissMutation.mutate(n.id)}
                className="text-blush-400 hover:text-blush-600 text-xs flex-shrink-0 mt-0.5"
              >
                Dismiss
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-5 pb-4 pr-1">
        {messages.map((msg, i) => (
          <div key={i} className={`flex items-end gap-2.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-blush-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 mb-0.5 shadow-pink">✦</div>
            )}
            <div className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'bg-blush-500 text-white rounded-br-md shadow-pink'
                : 'bg-white border border-gray-100 text-gray-800 rounded-bl-md shadow-sm'
            }`}>
              <MessageBody content={msg.content} />
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex items-end gap-2.5 justify-start">
            <div className="w-8 h-8 rounded-full bg-blush-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 shadow-pink">✦</div>
            <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
              <TypingDots />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="pt-4 border-t border-gray-100">
        <div className="flex gap-3 bg-white border border-gray-200 rounded-2xl px-4 py-2.5 shadow-sm transition-all focus-within:border-blush-300 focus-within:ring-2 focus-within:ring-blush-100">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
            placeholder="Ask about products, share what you love…"
            className="flex-1 text-sm text-gray-800 placeholder-gray-400 bg-transparent focus:outline-none py-1"
          />
          <button
            onClick={send}
            disabled={isLoading || !input.trim()}
            className="px-5 py-2 bg-blush-500 hover:bg-blush-600 disabled:opacity-40 text-white font-semibold rounded-xl transition-all text-sm shadow-pink hover:shadow-pink-lg disabled:shadow-none"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

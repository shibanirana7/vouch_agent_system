import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'

interface ClientInfo {
  client_id: string
  client_name: string
  redirect_uri: string
}

export default function OAuthAuthorize() {
  const [params] = useSearchParams()
  const clientId = params.get('client_id') ?? ''
  const redirectUri = params.get('redirect_uri') ?? ''
  const state = params.get('state') ?? ''

  const [client, setClient] = useState<ClientInfo | null>(null)
  const [error, setError] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!clientId || !redirectUri) {
      setError('Missing client_id or redirect_uri')
      return
    }
    fetch(`/api/oauth/client-info?client_id=${encodeURIComponent(clientId)}&redirect_uri=${encodeURIComponent(redirectUri)}`)
      .then((r) => r.ok ? r.json() : r.json().then((e) => Promise.reject(e.detail)))
      .then(setClient)
      .catch((e) => setError(typeof e === 'string' ? e : 'Unknown client'))
  }, [clientId, redirectUri])

  async function submit(action: 'allow' | 'deny') {
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/oauth/authorize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId, redirect_uri: redirectUri, state, email, password, action }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? 'Request failed')
      window.location.href = data.redirect_url
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
      setLoading(false)
    }
  }

  if (error && !client) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center p-8">
        <div className="bg-red-50 border border-red-100 rounded-2xl px-6 py-5 text-sm text-red-600 max-w-sm text-center">
          {error}
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="bg-white rounded-3xl shadow-sm border border-gray-100 w-full max-w-md p-10">
        {/* Brand */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <span className="text-2xl font-bold text-blush-500 tracking-tight">vouch</span>
          <span className="text-gray-300 text-xl">↔</span>
          <span className="text-sm font-semibold text-gray-700">{client?.client_name ?? '…'}</span>
        </div>

        <h2 className="text-xl font-bold text-gray-900 text-center mb-1">Authorize access</h2>
        <p className="text-sm text-gray-500 text-center mb-8">
          <span className="font-semibold text-gray-700">{client?.client_name}</span> wants to act as your
          Vouch shopping agent — reading your preferences and sending messages on your behalf.
        </p>

        {/* Permissions list */}
        <ul className="space-y-2 mb-8">
          {[
            'Send messages to your shopping agent',
            'Read recommendations from your trust network',
            'Share product reviews on your behalf',
          ].map((perm) => (
            <li key={perm} className="flex items-center gap-3 text-sm text-gray-600">
              <span className="w-5 h-5 rounded-full bg-blush-50 border border-blush-200 flex items-center justify-center text-blush-500 text-xs flex-shrink-0">
                ✓
              </span>
              {perm}
            </li>
          ))}
        </ul>

        {/* Login form */}
        <div className="space-y-4 mb-6">
          <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-widest">
            Sign in to confirm it&apos;s you
          </p>
          <input
            type="email"
            required
            autoFocus
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
          />
          <input
            type="password"
            required
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit('allow')}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
          />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 text-sm text-red-600 mb-4">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={() => submit('deny')}
            disabled={loading}
            className="flex-1 py-3 border border-gray-200 rounded-full text-sm font-semibold text-gray-500 hover:bg-gray-50 disabled:opacity-40 transition-all"
          >
            Deny
          </button>
          <button
            onClick={() => submit('allow')}
            disabled={loading || !email || !password}
            className="flex-1 py-3 bg-blush-500 hover:bg-blush-600 disabled:opacity-40 text-white text-sm font-semibold rounded-full transition-all shadow-pink"
          >
            {loading ? 'Authorizing…' : 'Allow'}
          </button>
        </div>

        <p className="text-[11px] text-gray-400 text-center mt-6 leading-relaxed">
          You can revoke access at any time from your Vouch profile.
        </p>
      </div>
    </div>
  )
}

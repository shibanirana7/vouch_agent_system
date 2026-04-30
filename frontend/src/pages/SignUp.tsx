import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createUser } from '../api/client'
import { useAuthStore } from '../store/auth'

export default function SignUp() {
  const navigate = useNavigate()
  const setUser = useAuthStore((s) => s.setUser)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const user = await createUser({ name, email, password, is_agent_user: false })
      setUser(user.id, user.agent_id!, user.name)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-white flex">
      {/* Left panel — decorative */}
      <div className="hidden lg:flex w-2/5 bg-blush-500 flex-col justify-between p-14 relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              'radial-gradient(ellipse at 15% 85%, rgba(255,133,191,0.5) 0%, transparent 55%), radial-gradient(ellipse at 85% 10%, rgba(255,194,223,0.4) 0%, transparent 50%)',
          }}
        />
        <div className="relative z-10">
          <span className="text-2xl font-bold text-white tracking-tight">vouch</span>
        </div>
        <div className="relative z-10">
          <p className="text-4xl font-light text-white leading-tight mb-6">
            Beauty recommendations
            <br />
            <span className="font-bold">from people you trust.</span>
          </p>
          <p className="text-xs text-blush-100 font-semibold uppercase tracking-[0.2em]">
            Trust-first shopping
          </p>
        </div>
        <div className="relative z-10 flex gap-6">
          {['AI-powered', 'Trust network', 'Personal picks'].map((tag) => (
            <span key={tag} className="text-xs text-blush-200 font-medium">
              {tag}
            </span>
          ))}
        </div>
      </div>

      {/* Right panel — form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-md">
          <div className="mb-10 lg:hidden">
            <span className="text-2xl font-bold text-blush-500 tracking-tight">vouch</span>
          </div>

          <h2 className="text-3xl font-bold text-gray-900 tracking-tight mb-1">
            Create your account
          </h2>
          <p className="text-sm text-gray-500 mb-10">
            Join the beauty community that shops smarter.
          </p>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-widest mb-2">
                Name
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blush-300 focus:border-blush-300 bg-gray-50 text-sm transition-all"
                placeholder="Your name"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-widest mb-2">
                Email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blush-300 focus:border-blush-300 bg-gray-50 text-sm transition-all"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-widest mb-2">
                Password
              </label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blush-300 focus:border-blush-300 bg-gray-50 text-sm transition-all"
                placeholder="At least 8 characters"
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 text-sm text-red-600">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-4 bg-blush-500 hover:bg-blush-600 disabled:opacity-50 text-white font-semibold rounded-full transition-all shadow-pink hover:shadow-pink-lg text-sm uppercase tracking-widest"
            >
              {loading ? 'Creating your account…' : 'Join Vouch'}
            </button>
          </form>

          <p className="mt-8 text-center text-sm text-gray-500">
            Already have an account?{' '}
            <Link to="/login" className="text-blush-500 font-semibold hover:text-blush-600 transition-colors">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}

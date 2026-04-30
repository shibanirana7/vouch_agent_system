import { Outlet, NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../store/auth'
import { getConnectionRequests } from '../api/client'

const navItems = [
  { to: '/', label: 'Chat' },
  { to: '/feed', label: 'Agent Feed' },
  { to: '/wishlist', label: 'Wishlist' },
  { to: '/purchases', label: 'Purchases' },
  { to: '/social', label: 'My Network' },
  { to: '/profile', label: 'Profile' },
]

export default function Layout() {
  const { userName, logout, agentId } = useAuthStore()

  const { data: pendingRequests = [] } = useQuery({
    queryKey: ['connection-requests', agentId],
    queryFn: () => getConnectionRequests(agentId!),
    enabled: !!agentId,
    refetchInterval: 30000,
  })
  const pendingCount = pendingRequests.length

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <header className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-gray-100 px-8 py-0 h-14 grid grid-cols-3 items-center">
        {/* Brand */}
        <div className="flex items-center gap-4">
          <span className="text-xl font-bold tracking-tight text-blush-500 leading-none">vouch</span>
          <span className="hidden sm:block text-[10px] uppercase tracking-widest text-gray-400 font-semibold border-l border-gray-200 pl-4">
            trust-first shopping
          </span>
        </div>

        {/* Nav — centered */}
        <nav className="flex items-center justify-center gap-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `relative px-4 h-14 flex items-center justify-center text-center text-xs font-semibold uppercase tracking-widest transition-all border-b-2 ${
                  isActive
                    ? 'text-blush-500 border-blush-500'
                    : 'text-gray-500 border-transparent hover:text-gray-900 hover:border-gray-200'
                }`
              }
            >
              {item.label}
              {item.to === '/social' && pendingCount > 0 && (
                <span className="absolute top-3 right-1 w-4 h-4 rounded-full bg-blush-500 text-white text-[9px] font-bold flex items-center justify-center">
                  {pendingCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="flex items-center justify-end gap-4">
          <span className="text-sm font-medium text-gray-700 hidden sm:block">{userName}</span>
          <button
            onClick={logout}
            className="text-[11px] font-semibold uppercase tracking-widest text-gray-400 hover:text-blush-500 transition-colors"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="flex-1 p-6 max-w-5xl mx-auto w-full">
        <Outlet />
      </main>
    </div>
  )
}

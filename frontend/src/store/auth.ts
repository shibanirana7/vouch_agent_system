import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  userId: string | null
  agentId: string | null
  userName: string | null
  bearerToken: string | null
  setUser: (userId: string, agentId: string, userName: string) => void
  setBearerToken: (token: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      userId: null,
      agentId: null,
      userName: null,
      bearerToken: null,
      setUser: (userId, agentId, userName) => set({ userId, agentId, userName }),
      setBearerToken: (token) => set({ bearerToken: token }),
      logout: () => {
        set({ userId: null, agentId: null, userName: null, bearerToken: null })
        // Clear persisted chat so next user starts fresh
        import('./chat').then(({ useChatStore }) => useChatStore.getState().clearMessages())
      },
    }),
    { name: 'vouch-auth' }
  )
)

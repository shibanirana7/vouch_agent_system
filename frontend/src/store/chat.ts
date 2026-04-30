import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ChatState {
  messages: Message[]
  isLoading: boolean
  addMessage: (msg: Message) => void
  setLoading: (loading: boolean) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      messages: [],
      isLoading: false,
      addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
      setLoading: (loading) => set({ isLoading: loading }),
      clearMessages: () => set({ messages: [], isLoading: false }),
    }),
    {
      name: 'vouch-chat',
      // Don't persist isLoading — a page reload while mid-request should start fresh
      partialize: (s) => ({ messages: s.messages }),
    }
  )
)

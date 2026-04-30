const BASE: string = import.meta.env.VITE_API_BASE ?? '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 180_000) // 180s timeout (multiple LLM calls)
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    signal: controller.signal,
    ...init,
  }).finally(() => clearTimeout(timeout))
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'Request failed')
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ── Users ─────────────────────────────────────────────────────────────────────

export interface UserOut {
  id: string
  name: string
  email: string
  is_agent_user: boolean
  created_at: string
  agent_id: string | null
}

export const createUser = (body: { name: string; email: string; password: string; is_agent_user: boolean }) =>
  request<UserOut>('/users', { method: 'POST', body: JSON.stringify(body) })

export const login = (body: { email: string; password: string }) =>
  request<UserOut>('/users/login', { method: 'POST', body: JSON.stringify(body) })

export const getSelfToken = (agentId: string) =>
  request<{ access_token: string; token_type: string; agent_id: string }>(
    '/oauth/self-token',
    { method: 'POST', body: JSON.stringify({ agent_id: agentId }) }
  )

export const getUser = (userId: string) => request<UserOut>(`/users/${userId}`)

export const searchUsers = (q: string) =>
  request<{ name: string; agent_id: string }[]>(`/users/search?q=${encodeURIComponent(q)}`)

// ── Agents ────────────────────────────────────────────────────────────────────

export interface ChatResponse {
  response: string
  agent_id: string
}

export interface A2ATask {
  id: string
  contextId: string
  status: {
    state: string
    message: {
      role: string
      parts: { kind: string; text: string }[]
      messageId: string
    }
  }
}

export interface A2AEnvelope {
  request: object
  response: A2ATask
}

export async function chatViaA2A(
  agentId: string,
  message: string,
  bearerToken: string,
): Promise<A2AEnvelope> {
  const messageId = crypto.randomUUID()
  const taskId = crypto.randomUUID()
  const contextId = crypto.randomUUID()
  const requestBody = {
    message: {
      role: 'user',
      parts: [{ kind: 'text', text: message }],
      messageId,
    },
    configuration: {},
    metadata: { source: 'vouch-ui', protocol: 'a2a', timestamp: new Date().toISOString() },
    taskId,
    contextId,
  }
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 180_000)
  const res = await fetch(`${BASE}/a2a/agents/${agentId}/message/send`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${bearerToken}`,
    },
    body: JSON.stringify(requestBody),
    signal: controller.signal,
  }).finally(() => clearTimeout(timeout))
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'A2A request failed')
  }
  const response: A2ATask = await res.json()
  return { request: requestBody, response }
}

export const chatWithAgent = (
  agentId: string,
  message: string,
  history: { role: string; content: string }[] = [],
) =>
  request<ChatResponse>(`/agents/${agentId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message, history }),
  })

export interface AgentOut {
  id: string
  user_id: string
  preference_summary: Record<string, unknown>
  is_autonomous: boolean
  created_at: string
  updated_at: string
}

export const getAgent = (agentId: string) =>
  request<AgentOut>(`/agents/${agentId}`)

export const setAutonomous = (agentId: string, enabled: boolean) =>
  request<{ agent_id: string; is_autonomous: boolean }>(
    `/agents/${agentId}/autonomous?enabled=${enabled}`,
    { method: 'PATCH' }
  )

// ── Wishlist ──────────────────────────────────────────────────────────────────

export interface WishlistItem {
  id: string
  product_name: string
  description: string
  url: string | null
  priority: number
  target_price: number | null
  is_recurring: boolean
  recurrence_interval_days: number | null
  created_at: string
}

export interface ProactiveAlert {
  wishlist_item_id: string
  product_name: string
  target_price: number
  found_at: number
  found_product: string
  savings: number
}

export const proactiveCheck = (agentId: string) =>
  request<{ alerts: ProactiveAlert[] }>(`/agents/${agentId}/proactive-check`, { method: 'POST' })

export const getPreferences = (agentId: string) =>
  request<{ preferences: string[]; purchase_history_summary: { text: string; product: string; price: number; category: string; satisfaction: number }[] }>(
    `/agents/${agentId}/preferences`
  )

export const getWishlist = (agentId: string) =>
  request<WishlistItem[]>(`/agents/${agentId}/wishlist`)

export const addWishlistItem = (
  agentId: string,
  body: { product_name: string; description?: string; target_price?: number; is_recurring?: boolean; priority?: number }
) =>
  request<WishlistItem>(`/agents/${agentId}/wishlist`, {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const removeWishlistItem = (agentId: string, itemId: string) =>
  request<void>(`/agents/${agentId}/wishlist/${itemId}`, { method: 'DELETE' })

export const confirmWishlistPurchase = (wishlistItemId: string, actualPrice?: number) =>
  request<{ status: string; purchase_id: string; product_name: string; price: number }>(
    '/shopping/confirm-wishlist-purchase',
    {
      method: 'POST',
      body: JSON.stringify({ wishlist_item_id: wishlistItemId, actual_price: actualPrice }),
    }
  )

// ── Purchases ─────────────────────────────────────────────────────────────────

export interface PurchaseRecord {
  id: string
  product_name: string
  url: string
  price: number
  was_recommended: boolean
  recommending_agent_id: string | null
  satisfaction_score: number | null
  opinion_text: string | null
  purchased_at: string
}

export const getPurchases = (agentId: string) =>
  request<PurchaseRecord[]>(`/agents/${agentId}/purchases`)

export const getReviews = (agentId: string) =>
  request<Record<string, { text: string; rating: number }>>(`/agents/${agentId}/reviews`)

export const ratePurchase = (purchaseId: string, opinion: string) =>
  request<{ status: string; sentiment_score: number; preferences_added: number }>(
    `/shopping/rate/${purchaseId}`,
    { method: 'POST', body: JSON.stringify({ opinion }) }
  )

export interface AgentNotification {
  id: string
  type: string
  title: string
  body: string
  action_type: string | null
  action_payload: Record<string, unknown> | null
  created_at: string
}

export const getNotifications = (agentId: string) =>
  request<AgentNotification[]>(`/agents/${agentId}/notifications`)

export const dismissNotification = (agentId: string, notifId: string) =>
  request<void>(`/agents/${agentId}/notifications/${notifId}/dismiss`, { method: 'PATCH' })

// ── Shopping decisions ────────────────────────────────────────────────────────

export const decidePurchase = (agentId: string, query: string) =>
  request<{ agent_id: string; recommendation: string }>('/shopping/decide', {
    method: 'POST',
    body: JSON.stringify({ agent_id: agentId, query }),
  })

// ── Social / Trust ────────────────────────────────────────────────────────────

export interface TrustRelationship {
  id: string
  from_agent_id: string
  to_agent_id: string
  trust_level: 'close_friend' | 'friend' | 'acquaintance'
  trust_weight: number
  interaction_count: number
  created_at: string
}

export const getTrustNetwork = (agentId: string) =>
  request<TrustRelationship[]>(`/social/trust/${agentId}`)

export interface ConnectionRequest {
  id: string
  from_agent_id: string
  from_name: string
  message: string | null
  similarity_score: number | null
  created_at: string
}

export const getConnectionRequests = (agentId: string) =>
  request<ConnectionRequest[]>(`/social/connection-requests/${agentId}`)

export const respondToConnectionRequest = (requestId: string, action: 'accept' | 'deny', trustLevel = 'acquaintance') =>
  request<{ status: string }>(`/social/connection-requests/${requestId}/respond`, {
    method: 'PATCH',
    body: JSON.stringify({ action, trust_level: trustLevel }),
  })

export interface SentRequest {
  id: string
  to_agent_id: string
  to_name: string
  message: string | null
  similarity_score: number | null
  created_at: string
}

export const getSentRequests = (agentId: string) =>
  request<SentRequest[]>(`/social/sent-requests/${agentId}`)

export const createTrust = (fromAgentId: string, toAgentId: string, trustLevel: string) =>
  request<TrustRelationship>('/social/trust', {
    method: 'POST',
    body: JSON.stringify({ from_agent_id: fromAgentId, to_agent_id: toAgentId, trust_level: trustLevel }),
  })

export const updateTrust = (fromAgentId: string, toAgentId: string, trustLevel: string) =>
  request<TrustRelationship>(`/social/trust/${fromAgentId}/${toAgentId}`, {
    method: 'PATCH',
    body: JSON.stringify({ trust_level: trustLevel }),
  })

export const deleteTrust = (fromAgentId: string, toAgentId: string) =>
  request<void>(`/social/trust/${fromAgentId}/${toAgentId}`, { method: 'DELETE' })

export interface FriendReview {
  text: string
  product: string
  category: string
  rating: number
  agent_id: string
  trust_weight: number
}

export const getFriendReviews = (agentId: string) =>
  request<FriendReview[]>(`/social/friend-reviews/${agentId}`)

export interface AgentProfile {
  agent_id: string
  name: string
  reviews: { text: string; product: string; category: string; rating: number }[]
}

export const getAgentProfile = (agentId: string) =>
  request<AgentProfile>(`/social/profile/${agentId}`)

export interface Consultation {
  id: string
  from_agent_id: string
  to_agent_id: string
  query: string
  response: string
  trust_weight: number
  created_at: string
  direction: 'sent' | 'received'
  a2a_request: string | null
  a2a_response: string | null
}

export const getConsultations = (agentId: string) =>
  request<Consultation[]>(`/social/consultations/${agentId}`)

export const consultAgent = (fromAgentId: string, toAgentId: string, query: string) =>
  request<{ from_agent_id: string; to_agent_id: string; trust_weight: number; response: string }>(
    `/social/consult/${toAgentId}`,
    { method: 'POST', body: JSON.stringify({ from_agent_id: fromAgentId, query }) }
  )

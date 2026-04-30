import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getWishlist, addWishlistItem, confirmWishlistPurchase, removeWishlistItem, WishlistItem } from '../api/client'
import { useAuthStore } from '../store/auth'

const PRIORITY_LABELS: Record<number, string> = { 1: 'Low', 2: 'Medium', 3: 'High' }
const PRIORITY_COLORS: Record<number, string> = {
  1: 'bg-gray-100 text-gray-500',
  2: 'bg-yellow-50 text-yellow-600 border border-yellow-200',
  3: 'bg-blush-50 text-blush-600 border border-blush-200',
}

export default function Wishlist() {
  const agentId = useAuthStore((s) => s.agentId)!
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    product_name: '',
    description: '',
    target_price: '',
    priority: 1,
    is_recurring: false,
  })

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['wishlist', agentId],
    queryFn: () => getWishlist(agentId),
  })

  const addMutation = useMutation({
    mutationFn: () =>
      addWishlistItem(agentId, {
        product_name: form.product_name,
        description: form.description,
        target_price: form.target_price ? parseFloat(form.target_price) : undefined,
        priority: form.priority,
        is_recurring: form.is_recurring,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wishlist', agentId] })
      setShowForm(false)
      setForm({ product_name: '', description: '', target_price: '', priority: 1, is_recurring: false })
    },
  })

  const confirmMutation = useMutation({
    mutationFn: (item: WishlistItem) =>
      confirmWishlistPurchase(item.id, item.target_price ?? undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wishlist', agentId] })
      qc.invalidateQueries({ queryKey: ['purchases', agentId] })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (itemId: string) => removeWishlistItem(agentId, itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wishlist', agentId] }),
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
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Wishlist</h1>
          <p className="text-xs text-gray-400 uppercase tracking-widest font-medium mt-0.5">
            {items.length} {items.length === 1 ? 'item' : 'items'}
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-5 py-2.5 bg-blush-500 hover:bg-blush-600 text-white text-xs font-semibold rounded-full transition-all shadow-pink hover:shadow-pink-lg uppercase tracking-widest"
        >
          + Add item
        </button>
      </div>

      {/* Add form */}
      {showForm && (
        <div className="bg-white border border-gray-100 rounded-2xl p-6 mb-6 shadow-sm">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">
            New wishlist item
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <input
              placeholder="Product name *"
              value={form.product_name}
              onChange={(e) => setForm({ ...form, product_name: e.target.value })}
              className="col-span-2 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
            />
            <input
              placeholder="Description"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="col-span-2 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
            />
            <input
              type="number"
              placeholder="Target price ($)"
              value={form.target_price}
              onChange={(e) => setForm({ ...form, target_price: e.target.value })}
              className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
            />
            <select
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value) })}
              className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 bg-gray-50"
            >
              <option value={1}>Low priority</option>
              <option value={2}>Medium priority</option>
              <option value={3}>High priority</option>
            </select>
            <label className="flex items-center gap-2.5 text-sm text-gray-600 col-span-2">
              <input
                type="checkbox"
                checked={form.is_recurring}
                onChange={(e) => setForm({ ...form, is_recurring: e.target.checked })}
                className="accent-blush-500 w-4 h-4"
              />
              Recurring purchase
            </label>
          </div>
          <div className="flex gap-3 mt-4">
            <button
              onClick={() => addMutation.mutate()}
              disabled={!form.product_name || addMutation.isPending}
              className="px-5 py-2.5 bg-blush-500 hover:bg-blush-600 disabled:opacity-40 text-white text-xs font-semibold rounded-full transition-all shadow-pink uppercase tracking-widest"
            >
              {addMutation.isPending ? 'Adding…' : 'Add to wishlist'}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="px-4 py-2.5 text-sm text-gray-400 hover:text-gray-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <div className="text-5xl mb-4">✨</div>
          <p className="text-sm font-medium">Your wishlist is empty.</p>
          <p className="text-xs mt-1 text-gray-300">Add something you want, or ask your agent.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="bg-white border border-gray-100 rounded-2xl p-5 shadow-sm flex items-center justify-between hover:shadow-md transition-shadow"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="font-semibold text-gray-900">{item.product_name}</span>
                  <span className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${PRIORITY_COLORS[item.priority]}`}>
                    {PRIORITY_LABELS[item.priority]}
                  </span>
                  {item.is_recurring && (
                    <span className="text-xs px-2.5 py-0.5 rounded-full bg-mauve-50 text-mauve-600 border border-mauve-200 font-semibold">
                      Recurring
                    </span>
                  )}
                </div>
                {item.description && (
                  <p className="text-sm text-gray-500 mt-0.5">{item.description}</p>
                )}
                {item.target_price && (
                  <p className="text-sm text-blush-500 font-semibold mt-1">
                    Target: ${item.target_price}
                  </p>
                )}
              </div>
              <div className="ml-5 flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => confirmMutation.mutate(item)}
                  disabled={confirmMutation.isPending}
                  className="px-4 py-2 bg-gray-900 hover:bg-blush-500 disabled:opacity-40 text-white text-xs font-semibold rounded-full transition-all uppercase tracking-widest whitespace-nowrap"
                >
                  ✓ Purchased
                </button>
                <button
                  onClick={() => removeMutation.mutate(item.id)}
                  disabled={removeMutation.isPending}
                  className="px-3 py-2 text-gray-300 hover:text-red-500 disabled:opacity-40 text-xs font-semibold rounded-full hover:bg-red-50 transition-all"
                  title="Remove from wishlist"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

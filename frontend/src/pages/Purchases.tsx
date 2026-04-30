import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPurchases, ratePurchase, getReviews } from '../api/client'
import { useAuthStore } from '../store/auth'

export default function Purchases() {
  const agentId = useAuthStore((s) => s.agentId)!
  const qc = useQueryClient()

  const [pendingId, setPendingId] = useState<string | null>(null)
  const [comment, setComment] = useState('')

  const { data: purchases = [], isLoading } = useQuery({
    queryKey: ['purchases', agentId],
    queryFn: () => getPurchases(agentId),
  })

  const { data: reviews = {} } = useQuery({
    queryKey: ['reviews', agentId],
    queryFn: () => getReviews(agentId),
  })

  const rateMutation = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) => ratePurchase(id, text),
    onSuccess: () => {
      setPendingId(null)
      setComment('')
      qc.invalidateQueries({ queryKey: ['purchases', agentId] })
      setTimeout(() => qc.invalidateQueries({ queryKey: ['reviews', agentId] }), 5000)
      setTimeout(() => qc.invalidateQueries({ queryKey: ['trust', agentId] }), 3000)
    },
  })

  if (isLoading)
    return (
      <div className="text-center py-16 text-gray-400 text-sm uppercase tracking-widest">
        Loading…
      </div>
    )

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">Purchase History</h1>
        <p className="text-xs text-gray-400 uppercase tracking-widest font-medium mt-0.5">
          {purchases.length} {purchases.length === 1 ? 'purchase' : 'purchases'}
        </p>
      </div>

      {purchases.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <div className="text-5xl mb-4">🛍️</div>
          <p className="text-sm font-medium">No purchases yet.</p>
          <p className="text-xs mt-1 text-gray-300">
            Confirm a wishlist item or ask your agent to help you shop!
          </p>
        </div>
      ) : (
        <div className="grid gap-4">
          {purchases.map((p) => {
            const review = reviews[p.product_name.toLowerCase()]
            const hasOpinion = !!p.opinion_text
            const isEditing = pendingId === p.id

            return (
              <div
                key={p.id}
                className="bg-white border border-gray-100 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow"
              >
                {/* Header row */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 leading-tight">{p.product_name}</h3>
                    <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                      <span className="text-blush-500 font-bold text-sm">${p.price.toFixed(2)}</span>
                      <span className="text-xs text-gray-400">
                        {new Date(p.purchased_at).toLocaleDateString('en-US', {
                          month: 'short', day: 'numeric', year: 'numeric',
                        })}
                      </span>
                      {p.was_recommended && (
                        <span className="text-xs bg-mauve-50 text-mauve-600 border border-mauve-200 px-2.5 py-0.5 rounded-full font-semibold">
                          Recommended
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Edit / Add button — always visible when not editing */}
                  {!isEditing && (
                    <button
                      onClick={() => { setPendingId(p.id); setComment(p.opinion_text ?? '') }}
                      title={hasOpinion ? 'Edit your comment' : 'Add a comment'}
                      className="flex-shrink-0 flex items-center gap-1.5 text-xs font-semibold text-blush-400 hover:text-blush-600 px-3 py-1.5 rounded-full hover:bg-blush-50 transition-all border border-transparent hover:border-blush-100"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                      {hasOpinion ? 'Edit' : 'Add comment'}
                    </button>
                  )}
                </div>

                {/* Saved comment — prominent block */}
                {hasOpinion && !isEditing && (
                  <div className="mt-4 bg-gray-50 rounded-xl px-4 py-3 border border-gray-100">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Your comment</p>
                    <p className="text-sm text-gray-700 leading-relaxed">{p.opinion_text}</p>
                  </div>
                )}

                {/* Fallback to shared review when no personal comment yet */}
                {!hasOpinion && review && !isEditing && (
                  <div className="mt-4 bg-gray-50 rounded-xl px-4 py-3 border border-gray-100">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Review</p>
                    <p className="text-sm text-gray-600 italic leading-relaxed">
                      {review.text.replace(/^\[.*?\]\s*[^:]+:\s*/, '')}
                    </p>
                  </div>
                )}

                {/* No comment yet — subtle prompt */}
                {!hasOpinion && !review && !isEditing && (
                  <button
                    onClick={() => { setPendingId(p.id); setComment('') }}
                    className="mt-3 w-full text-left px-4 py-3 rounded-xl border border-dashed border-gray-200 text-xs text-gray-400 hover:border-blush-200 hover:text-blush-400 transition-all"
                  >
                    + What did you think of this? Your agent will learn from it.
                  </button>
                )}

                {/* Edit form */}
                {isEditing && (
                  <div className="mt-4 border-t border-gray-100 pt-4">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                      {hasOpinion ? 'Update your comment' : 'What did you think?'}
                    </p>
                    <textarea
                      autoFocus
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      rows={3}
                      className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blush-200 resize-none bg-gray-50"
                      placeholder={`e.g. "The coverage was amazing but felt heavy by midday — great for dry skin"`}
                    />
                    <p className="text-[11px] text-gray-400 mt-1.5">
                      Your agent extracts your preferences from this and shares a review with trusted connections.
                    </p>
                    <div className="flex gap-3 mt-3 items-center">
                      <button
                        onClick={() => rateMutation.mutate({ id: p.id, text: comment })}
                        disabled={!comment.trim() || rateMutation.isPending}
                        className="px-5 py-2 bg-blush-500 hover:bg-blush-600 disabled:opacity-40 text-white text-xs font-semibold rounded-full transition-all shadow-pink uppercase tracking-widest"
                      >
                        {rateMutation.isPending ? 'Saving…' : 'Save'}
                      </button>
                      <button
                        onClick={() => { setPendingId(null); setComment('') }}
                        className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

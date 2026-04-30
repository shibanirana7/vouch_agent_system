import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getAgentProfile } from '../api/client'

const SENTIMENT_LABEL: Record<number, { label: string; cls: string }> = {
  1: { label: 'Disliked', cls: 'text-red-400 bg-red-50' },
  2: { label: 'Meh', cls: 'text-orange-400 bg-orange-50' },
  3: { label: 'Okay', cls: 'text-gray-400 bg-gray-50' },
  4: { label: 'Liked it', cls: 'text-lime-600 bg-lime-50' },
  5: { label: 'Loved it', cls: 'text-green-600 bg-green-50' },
}

export default function FriendProfile() {
  const { agentId } = useParams<{ agentId: string }>()
  const navigate = useNavigate()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['profile', agentId],
    queryFn: () => getAgentProfile(agentId!),
    enabled: !!agentId,
  })

  if (isLoading)
    return (
      <div className="text-center py-16 text-gray-400 text-sm uppercase tracking-widest">
        Loading…
      </div>
    )

  if (isError || !data)
    return (
      <div className="text-center py-16 text-gray-400">
        <p className="text-sm">Could not load profile.</p>
        <button onClick={() => navigate(-1)} className="mt-4 text-xs text-blush-500 hover:underline">
          ← Back
        </button>
      </div>
    )

  const initials = data.name.slice(0, 2).toUpperCase()

  return (
    <div className="max-w-2xl">
      <button
        onClick={() => navigate(-1)}
        className="text-xs text-gray-400 hover:text-gray-600 mb-6 inline-block"
      >
        ← Back to network
      </button>

      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <div
          className="w-14 h-14 rounded-full flex items-center justify-center text-base font-bold text-white flex-shrink-0 shadow-pink"
          style={{ background: 'linear-gradient(135deg, #ff4da0 0%, #ff0066 100%)' }}
        >
          {initials}
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">{data.name}</h1>
          <p className="text-[11px] text-gray-400 font-mono mt-0.5 select-all">{data.agent_id}</p>
        </div>
      </div>

      {/* Reviews */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">
          Reviews{data.reviews.length > 0 && (
            <span className="ml-2 text-blush-500 normal-case font-semibold">{data.reviews.length}</span>
          )}
        </h2>

        {data.reviews.length === 0 ? (
          <div className="text-center py-12 text-gray-400 text-sm">
            No reviews written yet.
          </div>
        ) : (
          <div className="grid gap-3">
            {data.reviews.map((r, i) => {
              const cleanText = r.text
                .replace(/^\[.*?\]\s*[^:]+:\s*/, '')
                .replace(/\s*\(rating:.*\)$/, '')
              return (
                <div key={i} className="bg-white border border-gray-100 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-gray-800 text-sm">{r.product}</p>
                      <p className="text-[11px] text-gray-400 capitalize mt-0.5">{r.category}</p>
                    </div>
                    {r.rating && SENTIMENT_LABEL[r.rating] && (
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${SENTIMENT_LABEL[r.rating].cls}`}>
                        {SENTIMENT_LABEL[r.rating].label}
                      </span>
                    )}
                  </div>
                  {cleanText && (
                    <p className="mt-2 text-xs text-gray-500 italic leading-relaxed border-t border-gray-50 pt-2">
                      "{cleanText}"
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </section>

    </div>
  )
}

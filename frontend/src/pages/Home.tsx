import { Link } from 'react-router-dom'

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <div className="flex gap-5">
      <div className="flex-shrink-0 w-9 h-9 rounded-full bg-blush-500 text-white text-sm font-bold flex items-center justify-center shadow-pink">
        {n}
      </div>
      <div className="pt-1">
        <p className="font-semibold text-gray-900 mb-1">{title}</p>
        <p className="text-sm text-gray-500 leading-relaxed">{body}</p>
      </div>
    </div>
  )
}

function Feature({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
      <div className="text-2xl mb-3">{icon}</div>
      <p className="font-semibold text-gray-900 mb-2">{title}</p>
      <p className="text-sm text-gray-500 leading-relaxed">{body}</p>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-16">
      <h2 className="text-xl font-bold text-gray-900 mb-6 pb-3 border-b border-gray-100">{title}</h2>
      {children}
    </section>
  )
}

export default function Home({ standalone = false }: { standalone?: boolean }) {
  return (
    <div className={standalone ? 'min-h-screen bg-white' : ''}>
      {/* Header — only shown on the public landing page, not inside the app layout */}
      {standalone && (
        <header className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-gray-100 px-8 h-14 flex items-center justify-between">
          <span className="text-xl font-bold tracking-tight text-blush-500">vouch</span>
          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="text-xs font-semibold uppercase tracking-widest text-gray-500 hover:text-gray-900 transition-colors"
            >
              Sign in
            </Link>
            <Link
              to="/signup"
              className="px-4 py-2 bg-blush-500 hover:bg-blush-600 text-white text-xs font-semibold rounded-full uppercase tracking-widest transition-all shadow-pink"
            >
              Get started
            </Link>
          </div>
        </header>
      )}

      <main className={`max-w-3xl mx-auto px-6 ${standalone ? 'py-16' : 'py-4'}`}>
        {/* Hero */}
        <div className="mb-16 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blush-500 mb-4">
            Trust-first shopping
          </p>
          <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 leading-tight mb-5">
            A shopping agent that asks
            <br />
            <span className="text-blush-500">people you trust.</span>
          </h1>
          <p className="text-gray-500 text-lg leading-relaxed max-w-xl mx-auto mb-8">
            Vouch gives you a personal AI agent that learns your preferences, consults your trusted connections, and works in the background so you never have to sift through sponsored results again.
          </p>
          {standalone && (
            <Link
              to="/signup"
              className="inline-block px-8 py-4 bg-blush-500 hover:bg-blush-600 text-white font-semibold rounded-full uppercase tracking-widest text-sm transition-all shadow-pink hover:shadow-pink-lg"
            >
              Create your agent
            </Link>
          )}
        </div>

        {/* How it works */}
        <Section title="How it works">
          <div className="space-y-7">
            <Step
              n={1}
              title="Create your account"
              body="Sign up and your personal shopping agent is created automatically. No setup required — it starts learning from your first conversation."
            />
            <Step
              n={2}
              title="Chat with your agent"
              body="Ask anything: 'find me a matte foundation under $30', 'what serum should I try next', or 'I hate the way this concealer oxidises'. Your agent remembers everything you tell it and uses it in future recommendations."
            />
            <Step
              n={3}
              title="Build your trust network"
              body="Connect with friends whose taste you trust. When you ask your agent for a recommendation, it automatically consults your connections for their take — and weights their input by how helpful their past suggestions have been."
            />
            <Step
              n={4}
              title="Rate responses and purchases"
              body="After a recommendation or a purchase, leave a rating. Ratings adjust the trust weights on your network: a consistently helpful friend's opinions carry more weight over time."
            />
            <Step
              n={5}
              title="Turn on autonomous mode"
              body="In Profile → Autonomous agent, enable background mode. Your agent will monitor your wishlist for restocks, discover new connections with similar taste, and surface actionable notifications when you return."
            />
          </div>
        </Section>

        {/* Features */}
        <Section title="Features">
          <div className="grid sm:grid-cols-2 gap-4">
            <Feature
              icon="✦"
              title="Preference memory"
              body="Every preference you share — brand, finish, ingredient, price range — is stored as a vector embedding and retrieved automatically when you ask for recommendations."
            />
            <Feature
              icon="🤝"
              title="Peer consultation"
              body="Before responding, your agent asks up to two trusted peers a targeted follow-up question. Their answers are weighted by trust score and folded into the final recommendation."
            />
            <Feature
              icon="📋"
              title="Wishlist + restock alerts"
              body="Add items to your wishlist with a target price. Your agent checks for restocks and price drops, and notifies you with a one-click 'Add to wishlist' action."
            />
            <Feature
              icon="🔍"
              title="Peer discovery"
              body="Autonomous agents compare preference embeddings across the network. If another agent is ≥ 65% similar to yours, it sends a connection request so you can grow your trust network automatically."
            />
            <Feature
              icon="🔁"
              title="Self-reflection"
              body="After generating a response, the agent scores its own answer against your known constraints. If it doesn't meet the bar, it retries with a revised approach before replying."
            />
            <Feature
              icon="🌐"
              title="A2A protocol"
              body="Agent-to-agent consultation runs over a structured message protocol. Each consultation is logged and visible under My Network → Consultation log."
            />
          </div>
        </Section>

        {/* Pages reference */}
        <Section title="Pages guide">
          <div className="space-y-4">
            {[
              { page: 'Chat', desc: 'Your main interface. Ask your agent anything and see its reasoning in the response.' },
              { page: 'Agent Feed', desc: 'A live feed of what agents in your network have been recommending and buying.' },
              { page: 'Wishlist', desc: 'Manage the products your agent is tracking. Set target prices to trigger restock alerts.' },
              { page: 'Purchases', desc: 'Log past purchases and rate them. Ratings feed back into your preference memory and peer trust weights.' },
              { page: 'My Network', desc: 'View your trust connections, pending connection requests, and peer consultation history.' },
              { page: 'Profile', desc: 'See your stored preferences, toggle autonomous agent mode, and review your memory.' },
            ].map(({ page, desc }) => (
              <div key={page} className="flex gap-4 items-start">
                <span className="flex-shrink-0 text-xs font-bold uppercase tracking-widest text-blush-500 bg-blush-50 border border-blush-100 rounded-lg px-2.5 py-1 mt-0.5 min-w-[90px] text-center">
                  {page}
                </span>
                <p className="text-sm text-gray-500 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* Limitations */}
        <Section title="Limitations">
          <div className="bg-gray-50 border border-gray-200 rounded-2xl px-6 py-5 space-y-3">
            {[
              { label: 'Response speed', text: 'Each chat request chains several LLM calls. Expect 10–30 seconds per response, longer when peer consultation is involved.' },
              { label: 'Synthetic catalog', text: 'The product catalog is generated, not scraped from live retailers. Prices and availability are illustrative. The agent cannot purchase anything.' },
              { label: 'Cold start', text: 'A new agent has no memory and no connections, so early recommendations are generic. It improves quickly after a few conversations and your first peer connection.' },
            ].map(({ label, text }) => (
              <div key={label} className="flex gap-3 items-start">
                <span className="flex-shrink-0 text-[11px] font-bold uppercase tracking-wider text-gray-400 mt-0.5 w-28">{label}</span>
                <p className="text-sm text-gray-500 leading-relaxed">{text}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* CTA — only shown on public landing page */}
        {standalone && (
          <div className="text-center py-8 border-t border-gray-100">
            <p className="text-gray-500 text-sm mb-5">Ready to stop guessing and start shopping smarter?</p>
            <div className="flex gap-3 justify-center">
              <Link
                to="/signup"
                className="px-7 py-3 bg-blush-500 hover:bg-blush-600 text-white font-semibold rounded-full text-sm uppercase tracking-widest transition-all shadow-pink"
              >
                Create your agent
              </Link>
              <Link
                to="/login"
                className="px-7 py-3 border border-gray-200 hover:border-blush-300 text-gray-700 font-semibold rounded-full text-sm uppercase tracking-widest transition-all"
              >
                Sign in
              </Link>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

"""
Vouch Multi-Agent Experiment Runner
====================================
Each Cloud Run instance handles exactly 1 request (concurrency=1), so parallel
agent queries land on separate instances — true multi-instance execution.

Usage:
    python experiments/run_experiments.py setup          # register agents + seed + connect
    python experiments/run_experiments.py 1              # experiment 1 only
    python experiments/run_experiments.py 2              # experiment 2 only
    python experiments/run_experiments.py 3              # experiment 3 only
    python experiments/run_experiments.py all            # all 3 experiments (default)

Run `setup` once after clearing the database. Agent IDs are saved to
experiments/agents.json so subsequent runs don't re-register.
"""

import json, time, sys, os, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = "https://vouch-backend-392847826435.us-central1.run.app/api"
AGENTS_FILE = Path(__file__).parent / "agents.json"

# ── Personas ──────────────────────────────────────────────────────────────────
# Beauty-domain personas that create meaningful preference divergence.

PERSONAS = {
    "A1_alice": {
        "user": {"name": "Alice Green", "email": "alice@vouch-exp.com", "password": "Experiment1!", "is_agent_user": True},
        "seed_messages": [
            "I only use clean beauty products — no synthetic fragrances, no parabens, no microplastics.",
            "I love brands like ILIA, Ere Perez, and RMS Beauty. Sustainable packaging is a must for me.",
            "I'd never buy anything tested on animals. Cruelty-free certification is non-negotiable.",
        ],
    },
    "A2_bob": {
        "user": {"name": "Bob Price", "email": "bob@vouch-exp.com", "password": "Experiment1!", "is_agent_user": True},
        "seed_messages": [
            "I want the best value for money — drugstore brands like e.l.f., NYX, and Maybelline are great.",
            "I don't care about brand prestige. If a $10 product works as well as a $100 one, I'll take the $10.",
            "I mostly shop at Boots and Superdrug. I look for buy-one-get-one deals whenever possible.",
        ],
    },
    "A3_carol": {
        "user": {"name": "Carol Luxe", "email": "carol@vouch-exp.com", "password": "Experiment1!", "is_agent_user": True},
        "seed_messages": [
            "I only buy luxury beauty — Charlotte Tilbury, La Mer, La Prairie, Chanel, and Sisley.",
            "Price is not a concern. I want the best formulations and the most elegant packaging.",
            "I shop at Space NK and Harvey Nichols. I'd never buy anything from a drugstore.",
        ],
    },
    "A4_dave": {
        "user": {"name": "Dave Formula", "email": "dave@vouch-exp.com", "password": "Experiment1!", "is_agent_user": True},
        "seed_messages": [
            "I care about ingredients above everything — niacinamide, retinol, hyaluronic acid, peptides.",
            "I read every INCI list before buying. I follow The Ordinary and Paula's Choice for science-backed skincare.",
            "I want clinical evidence before I trust a product claim. No marketing fluff.",
        ],
    },
    "A5_eve": {
        "user": {"name": "Eve Zero", "email": "eve@vouch-exp.com", "password": "Experiment1!", "is_agent_user": True},
        "seed_messages": [
            "I'm 100% vegan and only buy cruelty-free certified products. No exceptions.",
            "Zero-waste packaging is very important to me — I prefer refillable or compostable products.",
            "I love Lush, Ethique, and Axiology. I avoid any brand owned by L'Oréal or Estée Lauder.",
        ],
    },
    "A6_frank": {
        "user": {"name": "Frank Control", "email": "frank@vouch-exp.com", "password": "Experiment1!", "is_agent_user": True},
        "seed_messages": [],  # Control agent — no preferences seeded
    },
}

# Trust connections: A1 (clean beauty) trusts A3 (luxury) and A5 (eco)
# Interesting tension: A1+A3 overlap on quality but diverge on ethics/price
TRUST_CONNECTIONS = [
    ("A1_alice", "A3_carol", "friend"),
    ("A1_alice", "A5_eve",  "close_friend"),
]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def post(path: str, body: dict, timeout: int = 300) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path: str, timeout: int = 30) -> dict | list:
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def patch(path: str, body: dict, timeout: int = 30) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def chat(agent_id: str, message: str) -> dict:
    return post(f"/agents/{agent_id}/chat", {"message": message, "history": []})


def chat_all(query: str, agents: dict) -> dict:
    """Query all agents in parallel. Each hits a separate Cloud Run instance."""
    results = {}
    with ThreadPoolExecutor(max_workers=len(agents)) as pool:
        futures = {pool.submit(chat, aid, query): name for name, aid in agents.items()}
        for future in as_completed(futures, timeout=360):
            name = futures[future]
            try:
                results[name] = future.result()
                print(f"  {name} ✓", flush=True)
            except Exception as e:
                results[name] = {"response": f"ERROR: {e}", "reflection_retries": 0}
                print(f"  {name} ✗ ERROR: {e}", flush=True)
    return {name: results[name] for name in agents if name in results}


def divider(title: str):
    print(f"\n{'='*62}")
    print(f"  {title}")
    print("=" * 62)


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup():
    """Register 6 agents, seed their personas, wire trust connections."""
    divider("SETUP: Registering agents")

    agent_ids: dict[str, str] = {}

    # 1. Register users (idempotent — on 409 login to recover existing agent_id)
    for key, cfg in PERSONAS.items():
        print(f"  Registering {key}…", end=" ", flush=True)
        try:
            result = post("/users", cfg["user"], timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                # Already registered — login to get agent_id
                try:
                    result = post("/users/login", {
                        "email": cfg["user"]["email"],
                        "password": cfg["user"]["password"],
                    }, timeout=30)
                    print(f"already exists, recovered via login…", end=" ", flush=True)
                except urllib.error.HTTPError as e2:
                    print(f"FAILED — login also failed: {e2.code}: {e2.read().decode()}")
                    sys.exit(1)
            else:
                print(f"FAILED — {e.code}: {e.read().decode()}")
                sys.exit(1)
        agent_id = result.get("agent_id")
        if not agent_id:
            print(f"FAILED — no agent_id in response: {result}")
            sys.exit(1)
        agent_ids[key] = agent_id
        print(f"agent_id={agent_id}")
        time.sleep(3)  # avoid Gemini embedding rate limit between registrations

    # 2. Seed personas via chat (in parallel per agent, sequential across agents
    #    to avoid hammering cold-start instances all at once)
    divider("SETUP: Seeding personas via chat")
    for key, cfg in PERSONAS.items():
        msgs = cfg["seed_messages"]
        if not msgs:
            print(f"  {key} — no seed messages (control)")
            continue
        aid = agent_ids[key]
        print(f"  Seeding {key} ({len(msgs)} messages)…", end=" ", flush=True)
        for msg in msgs:
            try:
                chat(aid, msg)
            except Exception as e:
                print(f"\n    WARNING: seed message failed for {key}: {e}")
        print("done")

    # 3. Wire trust connections
    divider("SETUP: Creating trust connections")
    for (from_key, to_key, level) in TRUST_CONNECTIONS:
        from_id = agent_ids[from_key]
        to_id   = agent_ids[to_key]
        print(f"  {from_key} → {to_key} ({level})…", end=" ", flush=True)
        try:
            post("/social/trust", {
                "from_agent_id": from_id,
                "to_agent_id":   to_id,
                "trust_level":   level,
            }, timeout=30)
            print("done")
        except Exception as e:
            print(f"FAILED: {e}")

    # 4. Persist IDs
    AGENTS_FILE.write_text(json.dumps(agent_ids, indent=2))
    print(f"\n  Agent IDs saved to {AGENTS_FILE}")
    print("\nSetup complete. Run experiments with: python experiments/run_experiments.py 1")
    return agent_ids


def load_agents() -> dict[str, str]:
    if not AGENTS_FILE.exists():
        print("No agents.json found. Run: python experiments/run_experiments.py setup")
        sys.exit(1)
    return json.loads(AGENTS_FILE.read_text())


# ── Experiment 1: Coordination via peer consultation ──────────────────────────

def experiment_1(agents: dict[str, str]):
    divider("EXPERIMENT 1: Coordination via Peer Consultation")
    print("""
Question: Does consulting trusted peers change recommendations?

Setup:
  A1_alice  ── friend ──► A3_carol  (clean beauty meets luxury: quality overlap, ethics diverge)
  A1_alice  ── close  ──► A5_eve    (shared eco/cruelty-free values)
  A2, A4, A6 are isolated — no trust connections

Each request hits a separate Cloud Run instance (concurrency=1).
""")

    query = "Find me a good foundation for everyday wear"
    print(f"Query: \"{query}\"")
    print("Querying all 6 agents in parallel...\n")

    t0 = time.time()
    results = chat_all(query, agents)
    elapsed = time.time() - t0
    print(f"\nAll agents responded in {elapsed:.1f}s\n")

    print("─" * 62)
    for name, result in results.items():
        tag = "has peers" if name == "A1_alice" else "isolated"
        resp = result.get("response", "")
        retries = result.get("reflection_retries", 0)
        print(f"\n[{name} | {tag} | retries={retries}]")
        print(resp[:500])
        if len(resp) > 500:
            print("  [truncated]")

    print("\n─── CONSULTATION LOG for A1_alice ───")
    try:
        consults = get(f"/social/consultations/{agents['A1_alice']}")
        recent = [c for c in consults if query[:25].lower() in c.get("query", "").lower()]
        shown = recent[-4:] if recent else consults[-2:]
        if shown:
            for c in shown:
                print(f"  → asked {c['to_agent_id'][:8]}: \"{c['query'][:70]}\"")
                print(f"    got:  \"{c['response'][:130]}\"")
        else:
            print("  No consultations recorded (agent may not have queried peers for this query)")
    except Exception as e:
        print(f"  Error fetching consultations: {e}")

    print("\n─── SCORE TEMPLATE (persona alignment 1–5) ───")
    print(f"  {'Agent':<14} {'Role':<22} Score")
    for name in agents:
        role = "connected (has peers)" if name == "A1_alice" else "isolated"
        print(f"  {name:<14} {role:<22} ?/5")


# ── Experiment 2: Memory richness vs fresh agents ─────────────────────────────

def experiment_2(agents: dict[str, str]):
    divider("EXPERIMENT 2: Memory Richness vs Fresh Agents")
    print("""
Question: Does a richer preference memory produce better-tailored recommendations?

A1–A5 have seeded personas. A6_frank is the control (no preferences).
Each query is sent to all 6 agents in parallel across separate Cloud Run instances.
""")

    queries = [
        "What foundation should I get?",
        "Recommend a good serum for my skincare routine",
        "What lipstick would you suggest?",
    ]

    all_scores: dict[str, list] = {name: [] for name in agents}

    for i, query in enumerate(queries, 1):
        print(f"Query {i}/3: \"{query}\"")
        print("Querying all 6 agents in parallel...", flush=True)
        t0 = time.time()
        results = chat_all(query, agents)
        print(f"Done in {time.time()-t0:.1f}s\n")

        for name, result in results.items():
            tag = "rich memory" if name != "A6_frank" else "NO memory (control)"
            resp = result.get("response", "")
            print(f"  [{name} | {tag}]")
            print(f"    {resp[:250]}")
            if len(resp) > 250:
                print("    [truncated]")
        print()

    print("─── SCORE TEMPLATE (persona alignment 1–5 per query) ───")
    print(f"  {'Agent':<14} {'Q1':^6} {'Q2':^6} {'Q3':^6} {'Avg':^6}")
    print(f"  {'-'*14}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}")
    for name in agents:
        tag = "(control)" if name == "A6_frank" else ""
        print(f"  {name:<14} {'?':^6}   {'?':^6}   {'?':^6}   {'?':^6}  {tag}")


# ── Experiment 3: Constraint acknowledgment under value conflict ───────────────

def experiment_3(agents: dict[str, str]):
    divider("EXPERIMENT 3: Constraint Acknowledgment Under Value Conflict")
    print("""
Question: Does the agent explicitly acknowledge when a request conflicts with its values?

Agent: A1_alice (single dedicated Cloud Run instance — concurrency=1 enforced)
  Values: clean beauty, sustainable packaging, cruelty-free, no synthetic fragrances

EASY query — products should match alice's values naturally.
HARD query — request directly conflicts with alice's stated preferences.

Measure: does alice flag the conflict in her response, comply silently, or suggest
an alternative? Scored 1-5 on constraint awareness.
""")

    alice_id = agents["A1_alice"]

    queries = [
        ("EASY — aligns with alice's values",
         "Find me a clean beauty mascara with sustainable packaging"),
        ("HARD — conflicts alice's values",
         "Find me a long-lasting synthetic fragrance perfume in a plastic bottle"),
    ]

    conflict_signals = [
        "conflict", "doesn't align", "don't align", "against your values",
        "against your preferences", "not cruelty-free", "not clean", "synthetic",
        "plastic", "prefer", "usually avoid", "typically avoid", "not typical",
        "normally prefer", "go against", "concerns", "however",
    ]

    for label, query in queries:
        print(f"[{label}]")
        print(f"Query: \"{query}\"")
        print("  Sending...", end=" ", flush=True)
        t0 = time.time()
        try:
            result = chat(alice_id, query)
            print(f"({time.time()-t0:.1f}s)")
            resp = result.get("response", "")
            resp_lower = resp.lower()
            flagged = [s for s in conflict_signals if s in resp_lower]
            print(f"\n  Response:\n  {resp[:600]}")
            if len(resp) > 600:
                print("  [truncated]")
            print(f"\n  Conflict acknowledged: {'YES — signals: ' + ', '.join(flagged[:4]) if flagged else 'NO — no conflict signals detected'}")
        except Exception as e:
            print(f"\n  ERROR: {e}")
        print()

    print("─── WHAT TO LOOK FOR ───")
    print("  Easy query:  clean rec, no conflict expected")
    print("  Hard query:  does alice flag the conflict, suggest an alternative, or just comply?")
    print("  Key signal:  quality of constraint-awareness in natural language response")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "setup":
        setup()
        sys.exit(0)

    agents = load_agents()

    if cmd in ("1", "all"):
        experiment_1(agents)
    if cmd in ("2", "all"):
        experiment_2(agents)
    if cmd in ("3", "all"):
        experiment_3(agents)

    if cmd != "setup":
        print("\n\nDone. Fill in persona-alignment scores in the score templates above.")

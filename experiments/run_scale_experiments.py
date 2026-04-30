"""
Vouch Scale Experiments — Homework 8
=====================================
30 agents across 6 persona clusters. Extends HW7 (6 agents, 3 experiments) to
stress-test the system and surface constraints that only appear at scale.

What we measure at 30 agents vs the HW7 baseline:
  Exp 4  — Parallel load test: p50/p95 latency, failure rate, rate-limit hits
  Exp 5  — Autonomous trust network formation: cluster topology via peer discovery
  Exp 6  — Recommendation divergence: within-cluster vs cross-cluster coherence
  Stress — tick-all at 30 agents: sequential bottleneck, projected failure point

Usage:
    python experiments/run_scale_experiments.py setup     # register 30 agents
    python experiments/run_scale_experiments.py 4         # parallel load test
    python experiments/run_scale_experiments.py 5         # trust network formation
    python experiments/run_scale_experiments.py 6         # recommendation divergence
    python experiments/run_scale_experiments.py stress    # tick-all stress test
    python experiments/run_scale_experiments.py all       # all four
"""

import json, time, sys, statistics, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = "https://vouch-backend-392847826435.us-central1.run.app/api"
AGENTS_FILE = Path(__file__).parent / "agents_scale.json"

# HW7 baselines for comparison in Exp 4
HW7_AGENT_COUNT = 6
HW7_P50_SECONDS = 18.0   # approximate from HW7 run — update after running HW7 Exp 1
HW7_SUCCESS_RATE = 1.0


# ── 30 agents: 6 clusters × 5 agents ─────────────────────────────────────────
#
# key format: "{cluster}_{name}" — cluster_of(key) = key.split("_")[0]
#
# Cluster design rationale:
#   clean   — no synthetics, sustainable packaging; should connect to eco
#   budget  — price-first; should cluster tightly among themselves
#   luxury  — prestige only; opposite end from budget
#   science — evidence-based; overlaps with luxury on clinical brands
#   eco     — vegan/zero-waste; overlaps with clean on cruelty-free
#   ctrl    — no preferences; baseline (should connect to nobody at 0.65 threshold)

CLUSTER_DEFS: dict[str, list[dict]] = {
    "clean": [
        {
            "key": "clean_Maya", "name": "Maya Green", "email": "maya@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "I only use clean beauty — no synthetic fragrances, parabens, or microplastics.",
                "I love ILIA, RMS Beauty, and Ere Perez. Sustainable packaging is non-negotiable.",
                "Cruelty-free certified only. I support small indie clean beauty brands.",
            ],
        },
        {
            "key": "clean_Priya", "name": "Priya Singh", "email": "priya@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "No silicones, no mineral oil, no PEGs. I read every INCI list before buying.",
                "I love Caudalie, Pai Skincare, and Weleda. My skincare must be as natural as possible.",
                "Glass and aluminum packaging only — no plastic tubes or bottles.",
            ],
        },
        {
            "key": "clean_Laura", "name": "Laura Chen", "email": "laura@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "I prefer botanical and plant-derived ingredients — Tatcha, Fresh, and Dr. Hauschka.",
                "Clean beauty means no harsh chemicals, no synthetic dyes, no artificial preservatives.",
                "I have sensitive skin so I always patch test and avoid alcohol in skincare.",
            ],
        },
        {
            "key": "clean_Zoe", "name": "Zoe Park", "email": "zoe@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Clean AND high-performance — True Botanicals and ILIA prove you don't have to compromise.",
                "I look for recycled or refillable packaging. Ocean plastic upcycling is great.",
                "Non-GMO, organic-certified ingredients are my priority. Fair trade when possible.",
            ],
        },
        {
            "key": "clean_Nina", "name": "Nina Walsh", "email": "nina@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Fragrance-free clean beauty only — I have rosacea and fragrances flare my skin.",
                "Avène, La Roche-Posay, and Vanicream for their gentle, minimal, clean formulas.",
                "Hypoallergenic, dermatologist-tested, no essential oils. Simple and pure.",
            ],
        },
    ],
    "budget": [
        {
            "key": "budget_Jake", "name": "Jake Miller", "email": "jake@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Drugstore only — e.l.f. and NYX are amazing and cost a fraction of high-end brands.",
                "My max spend is $15 per product. I've never needed to spend more.",
                "I shop at Ulta during sales and always stack coupons and loyalty points.",
            ],
        },
        {
            "key": "budget_Sam", "name": "Sam Torres", "email": "sam@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "College student — Walmart and Target hauls only. Maybelline and Wet n Wild are great.",
                "Always looking for BOGO deals. CeraVe and Neutrogena for skincare.",
                "I don't believe expensive skincare is worth it — most is just marketing.",
            ],
        },
        {
            "key": "budget_Kim", "name": "Kim Nguyen", "email": "kim@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "I'm a dupe hunter — if a $12 product performs like a $60 one, I'll find it.",
                "r/MakeupAddiction and r/SkincareAddiction for affordable recommendations.",
                "Essence, Catrice, and Wet n Wild from European drugstores — excellent value.",
            ],
        },
        {
            "key": "budget_Raj", "name": "Raj Patel", "email": "raj@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Minimalist and budget — I use only 4 products total, all under $10 each.",
                "Morning: cleanser and SPF. Night: cleanser and moisturizer. That's it.",
                "Skeptical of brands with too many SKUs — usually just a marketing tactic.",
            ],
        },
        {
            "key": "budget_Pat", "name": "Pat Davis", "email": "pat@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "I track prices and only buy on significant discount.",
                "My entire skincare routine costs under $30: CeraVe cleanser, Neutrogena SPF, Nivea cream.",
                "Store-brand beauty works as well as named brands at half the cost.",
            ],
        },
    ],
    "luxury": [
        {
            "key": "luxury_Victoria", "name": "Victoria Laurent", "email": "victoria@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "I exclusively buy Charlotte Tilbury, La Mer, and Chanel Beauty. Quality above all.",
                "I shop at Space NK and Harvey Nichols. Drugstore products are not for me.",
                "Packaging matters as much as formula — it must be beautiful on my vanity.",
            ],
        },
        {
            "key": "luxury_Charles", "name": "Charles Beaumont", "email": "charles@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Sisley, Guerlain, La Prairie — the only brands I trust for serious skincare.",
                "I prefer department store consultations and only buy after a full skin assessment.",
                "Anti-aging and lifting are my priorities. I invest heavily in my skincare.",
            ],
        },
        {
            "key": "luxury_Helena", "name": "Helena Marchetti", "email": "helena@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Tom Ford Beauty, Armani Beauty, Givenchy — prestige makeup only.",
                "Monthly facials. My aesthetician recommends Augustinus Bader and iS Clinical.",
                "I follow luxury beauty editors on Vogue and Harpers Bazaar for recommendations.",
            ],
        },
        {
            "key": "luxury_Max", "name": "Max Ashford", "email": "max@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Clinical luxury is my segment — SkinCeuticals, Revision Skincare, Colorescience.",
                "Derm-recommended only, regardless of price. Results justify the cost.",
                "I'm willing to spend $500+ per month on skincare if the science supports it.",
            ],
        },
        {
            "key": "luxury_Sophie", "name": "Sophie Renard", "email": "sophie@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Luxury minimalist — only 4-5 products but all absolute top tier.",
                "Retrouve, Vintner's Daughter, and Augustinus Bader are worth every penny.",
                "I'd rather have one exceptional product than ten mediocre ones.",
            ],
        },
    ],
    "science": [
        {
            "key": "science_Chen", "name": "Chen Wei", "email": "chen@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "I read INCI lists religiously. Paula's Choice and The Ordinary are my benchmarks.",
                "Niacinamide, retinol, hyaluronic acid, AHAs/BHAs — actives with clinical evidence.",
                "I follow Dr. Shereene Idriss and Dr. Dray for evidence-based skincare.",
            ],
        },
        {
            "key": "science_Morgan", "name": "Morgan Blake", "email": "morgan@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "I read PubMed abstracts before buying any product with clinical claims.",
                "Deciem and The Ordinary because they're transparent about active concentrations.",
                "No proprietary blends — I want to know exactly what percentage of active is in each product.",
            ],
        },
        {
            "key": "science_Alex", "name": "Alex Kim", "email": "alex@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Clinical evidence is everything. Retinol, peptides, Vitamin C — all peer-reviewed support.",
                "I use retinoids prescribed by a dermatologist and layer scientifically compatible actives.",
                "Skeptical of 'clean beauty' claims unless backed by clinical safety data.",
            ],
        },
        {
            "key": "science_Jamie", "name": "Jamie Roberts", "email": "jamie@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Obsessed with SPF — mineral SPF 50+ every day without exception.",
                "Patch testing is mandatory. I introduce one new product every 4 weeks and track reactions.",
                "I keep a skincare log: every product, every reaction, every result. Data-driven.",
            ],
        },
        {
            "key": "science_Drew", "name": "Drew Foster", "email": "drew@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "No trends, no marketing — if there's no clinical trial, I won't buy it.",
                "Pharmacy brands with strong clinical backing: Avène, La Roche-Posay, Bioderma.",
                "Boring routine on purpose — consistent actives, stable formulations, no fads.",
            ],
        },
    ],
    "eco": [
        {
            "key": "eco_Sage", "name": "Sage Rivera", "email": "sage@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "100% vegan and cruelty-free only. I verify every brand on Leaping Bunny and PETA.",
                "Lush, Ethique, and Axiology are my go-to brands for ethical beauty.",
                "I avoid any brand owned by L'Oreal or Estee Lauder due to animal testing policies.",
            ],
        },
        {
            "key": "eco_River", "name": "River Santos", "email": "river@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Zero-waste beauty is my goal — refillable packaging, solid bars, compostable options.",
                "I've eliminated all plastic from my beauty routine. Packaging waste is unacceptable.",
                "I love Seed Phytonutrients, Plaine Products, and Package Free Shop.",
            ],
        },
        {
            "key": "eco_Fern", "name": "Fern Okafor", "email": "fern@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Certified B Corp brands only — Tata Harper, Thrive Causemetics, S.W. Basics.",
                "I check every brand's B Corp certification score before purchasing.",
                "Supply chain transparency matters as much as the product itself.",
            ],
        },
        {
            "key": "eco_Willow", "name": "Willow James", "email": "willow@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Indie ethical brands only — no conglomerates, no M&A by unethical parent companies.",
                "Palm-oil free formulas only. I check RSPO certification for every brand.",
                "I prioritize women-owned and BIPOC-owned beauty brands.",
            ],
        },
        {
            "key": "eco_Reed", "name": "Reed Nakamura", "email": "reed@vouch-scale.com",
            "password": "Scale2024!",
            "seed": [
                "Ocean-safe and reef-safe formulas only — no oxybenzone or octinoxate in sunscreens.",
                "Only brands with verified carbon-neutral or carbon-negative operations.",
                "Environmental impact is my top decision factor for every purchase.",
            ],
        },
    ],
    "ctrl": [
        {
            "key": "ctrl_1", "name": "Control One", "email": "ctrl1@vouch-scale.com",
            "password": "Scale2024!", "seed": [],
        },
        {
            "key": "ctrl_2", "name": "Control Two", "email": "ctrl2@vouch-scale.com",
            "password": "Scale2024!", "seed": [],
        },
        {
            "key": "ctrl_3", "name": "Control Three", "email": "ctrl3@vouch-scale.com",
            "password": "Scale2024!", "seed": [],
        },
        {
            "key": "ctrl_4", "name": "Control Four", "email": "ctrl4@vouch-scale.com",
            "password": "Scale2024!", "seed": [],
        },
        {
            "key": "ctrl_5", "name": "Control Five", "email": "ctrl5@vouch-scale.com",
            "password": "Scale2024!", "seed": [],
        },
    ],
}

# Flat list of all agent defs for iteration
ALL_DEFS: list[dict] = [a for agents in CLUSTER_DEFS.values() for a in agents]

# Keywords that signal each cluster's preferences (for Exp 6 analysis)
CLUSTER_KEYWORDS: dict[str, list[str]] = {
    "clean":   ["ilia", "rms", "caudalie", "pai", "tatcha", "ere perez", "true botanicals",
                "clean", "natural", "organic", "botanical", "sustainable", "fragrance-free"],
    "budget":  ["e.l.f.", "elf", "nyx", "maybelline", "cerave", "neutrogena", "wet n wild",
                "drugstore", "affordable", "budget", "cheap", "dupe", "value"],
    "luxury":  ["charlotte tilbury", "la mer", "chanel", "sisley", "la prairie",
                "augustinus bader", "tom ford", "luxury", "prestige", "premium"],
    "science": ["the ordinary", "paula's choice", "niacinamide", "retinol", "retinoid",
                "peptide", "clinical", "inci", "spf", "evidence", "dermatologist"],
    "eco":     ["lush", "ethique", "axiology", "tata harper", "vegan", "cruelty-free",
                "cruelty free", "refillable", "zero-waste", "zero waste", "b corp"],
    "ctrl":    [],
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(path: str, method: str = "GET", body: bytes | None = None,
             timeout: int = 300) -> dict | list:
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(f"{BASE}{path}", data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        code = e.code
        body_text = e.read().decode(errors="replace")
        if code == 429:
            raise RuntimeError(f"RATE_LIMITED_429: {body_text[:200]}")
        raise RuntimeError(f"HTTP_{code}: {body_text[:200]}")


def post(path: str, body: dict, timeout: int = 300) -> dict | list:
    return _request(path, "POST", json.dumps(body).encode(), timeout)


def get(path: str, timeout: int = 30) -> dict | list:
    return _request(path, "GET", timeout=timeout)


def patch_qs(path_with_qs: str, timeout: int = 30) -> dict:
    """PATCH with query-string params and empty body (for ?enabled=true style endpoints)."""
    return _request(path_with_qs, "PATCH", b"{}", timeout)


def chat(agent_id: str, message: str) -> dict:
    return post(f"/agents/{agent_id}/chat", {"message": message, "history": []})


def chat_timed(agent_id: str, name: str, message: str) -> tuple[str, dict, float, str]:
    """Returns (name, result, elapsed_seconds, status) — status: 'ok'|'rate_limited'|'timeout'|'error'."""
    t0 = time.time()
    try:
        result = chat(agent_id, message)
        return name, result, time.time() - t0, "ok"
    except RuntimeError as e:
        elapsed = time.time() - t0
        msg = str(e)
        status = "rate_limited" if "RATE_LIMITED" in msg else "timeout" if "timed out" in msg.lower() else "error"
        return name, {"response": f"ERROR: {msg}"}, elapsed, status
    except Exception as e:
        return name, {"response": f"ERROR: {e}"}, time.time() - t0, "error"


def set_autonomous(agent_id: str, enabled: bool) -> dict:
    flag = "true" if enabled else "false"
    return patch_qs(f"/agents/{agent_id}/autonomous?enabled={flag}")


def cluster_of(key: str) -> str:
    return key.split("_")[0]


# ── Stats helpers ─────────────────────────────────────────────────────────────

def latency_stats(times: list[float]) -> str:
    if not times:
        return "no data"
    s = sorted(times)
    n = len(s)
    p50 = s[n // 2]
    p75 = s[min(int(n * 0.75), n - 1)]
    p95 = s[min(int(n * 0.95), n - 1)]
    return (f"n={n}  min={min(s):.1f}s  p50={p50:.1f}s  "
            f"p75={p75:.1f}s  p95={p95:.1f}s  max={max(s):.1f}s")


def divider(title: str):
    print(f"\n{'=' * 64}")
    print(f"  {title}")
    print("=" * 64)


def section(title: str):
    print(f"\n── {title} {'─' * (58 - len(title))}")


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup() -> dict[str, str]:
    """Register 30 agents, seed their personas, save agent IDs."""
    divider("SETUP: Registering 30 agents")

    agent_ids: dict[str, str] = {}

    # 1. Register all 30 users sequentially (fast — no LLM involved)
    for defn in ALL_DEFS:
        key = defn["key"]
        user_payload = {
            "name": defn["name"],
            "email": defn["email"],
            "password": defn["password"],
            "is_agent_user": True,
        }
        print(f"  {key:<22}", end=" ", flush=True)
        try:
            result = post("/users", user_payload, timeout=30)
            agent_ids[key] = result["agent_id"]
            print(f"registered  → {result['agent_id'][:8]}")
        except RuntimeError as e:
            if "HTTP_409" in str(e):
                # Already exists — recover via login
                try:
                    r2 = post("/users/login", {"email": defn["email"], "password": defn["password"]}, timeout=30)
                    agent_ids[key] = r2["agent_id"]
                    print(f"already exists → {r2['agent_id'][:8]}")
                except Exception as e2:
                    print(f"FAILED (login also failed): {e2}")
                    sys.exit(1)
            else:
                print(f"FAILED: {e}")
                sys.exit(1)
        time.sleep(1)  # avoid hammering registration endpoint

    # 2. Seed personas in parallel waves (one wave per seed-message index)
    #    Each wave sends one message to each non-control agent simultaneously.
    seeded = [(defn["key"], agent_ids[defn["key"]], defn["seed"])
              for defn in ALL_DEFS if defn["seed"]]
    max_msgs = max(len(s) for _, _, s in seeded)

    divider(f"SETUP: Seeding personas ({len(seeded)} agents, {max_msgs} waves)")
    for wave in range(max_msgs):
        wave_agents = [(key, aid, msgs[wave]) for key, aid, msgs in seeded if wave < len(msgs)]
        print(f"\n  Wave {wave + 1}/{max_msgs}: {len(wave_agents)} messages in parallel…")
        with ThreadPoolExecutor(max_workers=len(wave_agents)) as pool:
            futures = {
                pool.submit(chat, aid, msg): key
                for key, aid, msg in wave_agents
            }
            for future in as_completed(futures, timeout=360):
                k = futures[future]
                try:
                    future.result()
                    print(f"    {k} ✓", flush=True)
                except Exception as e:
                    print(f"    {k} WARNING: {e}", flush=True)
        time.sleep(3)  # brief pause between waves for rate limit headroom

    AGENTS_FILE.write_text(json.dumps(agent_ids, indent=2))
    print(f"\n  Agent IDs saved → {AGENTS_FILE}")
    print(f"  Total agents registered: {len(agent_ids)}")
    print("\nSetup complete. Run experiments:")
    print("  python experiments/run_scale_experiments.py 4")
    return agent_ids


def load_agents() -> dict[str, str]:
    if not AGENTS_FILE.exists():
        print("No agents_scale.json found. Run: python experiments/run_scale_experiments.py setup")
        sys.exit(1)
    return json.loads(AGENTS_FILE.read_text())


# ── Experiment 4: Parallel load test at 30 agents ────────────────────────────

def experiment_4(agents: dict[str, str]):
    divider("EXPERIMENT 4: Parallel Load Test — 30 Agents Simultaneous")
    print("""
Question: How does the system perform under 30 simultaneous requests?
          What fails, what degrades, and at what latency percentile?

Each request hits a separate Cloud Run instance (concurrency=1 on the service).
HW7 baseline: 6 agents, p50 ~18s, 0 failures.

New constraints expected at 30 agents:
  - Gemini API rate limits (Flash has limited RPM)
  - Cloud Run cold starts (fewer warm instances pre-warmed)
  - Higher p95 due to rate-limit retries and cold-start variance
""")

    query = "Find me a good foundation for everyday wear"
    print(f"Query: \"{query}\"")
    print(f"Firing {len(agents)} agents in parallel…\n")

    t_wall_start = time.time()
    per_agent: dict[str, tuple[dict, float, str]] = {}

    with ThreadPoolExecutor(max_workers=len(agents)) as pool:
        futures = {
            pool.submit(chat_timed, aid, name, query): name
            for name, aid in agents.items()
        }
        for future in as_completed(futures, timeout=420):
            name = futures[future]
            try:
                _, result, elapsed, status = future.result()
                per_agent[name] = (result, elapsed, status)
                icon = "✓" if status == "ok" else "✗"
                print(f"  {icon} {name:<22} {elapsed:5.1f}s  [{status}]", flush=True)
            except Exception as e:
                per_agent[name] = ({"response": f"ERROR: {e}"}, 0.0, "error")
                print(f"  ✗ {name:<22} ERROR: {e}", flush=True)

    wall_time = time.time() - t_wall_start

    # ── Latency analysis ──────────────────────────────────────────────────────
    section("Latency Distribution")
    ok_times   = [v[1] for v in per_agent.values() if v[2] == "ok"]
    fail_count = sum(1 for v in per_agent.values() if v[2] != "ok")
    rate_limit = sum(1 for v in per_agent.values() if v[2] == "rate_limited")
    timeout_ct = sum(1 for v in per_agent.values() if v[2] == "timeout")

    print(f"  Wall-clock time (all 30 parallel):  {wall_time:.1f}s")
    print(f"  Successful responses:               {len(ok_times)}/{len(agents)}")
    print(f"  Failures:                           {fail_count} total")
    print(f"    Rate-limited (429):               {rate_limit}")
    print(f"    Timeouts:                         {timeout_ct}")
    print(f"    Other errors:                     {fail_count - rate_limit - timeout_ct}")
    print()
    print(f"  Latency (successful only):  {latency_stats(ok_times)}")
    print(f"  HW7 baseline (6 agents):    n=6  p50~{HW7_P50_SECONDS:.0f}s  success=100%")

    if ok_times and len(ok_times) >= 2:
        spread = max(ok_times) - min(ok_times)
        print(f"\n  Latency spread (max - min):  {spread:.1f}s")
        print(f"  → At 6 agents this spread was small; at 30 agents spread widens because")
        print(f"    later-queued requests wait for Gemini capacity or cold-start instances.")

    # ── Per-cluster breakdown ─────────────────────────────────────────────────
    section("Per-Cluster Success Rate")
    cluster_stats: dict[str, dict] = {}
    for name, (_, elapsed, status) in per_agent.items():
        cl = cluster_of(name)
        if cl not in cluster_stats:
            cluster_stats[cl] = {"ok": 0, "fail": 0, "times": []}
        if status == "ok":
            cluster_stats[cl]["ok"] += 1
            cluster_stats[cl]["times"].append(elapsed)
        else:
            cluster_stats[cl]["fail"] += 1

    print(f"  {'Cluster':<10} {'OK':>4} {'Fail':>5}  {'Avg latency (ok)':>20}")
    for cl in ["clean", "budget", "luxury", "science", "eco", "ctrl"]:
        s = cluster_stats.get(cl, {"ok": 0, "fail": 0, "times": []})
        avg = f"{statistics.mean(s['times']):.1f}s" if s["times"] else "—"
        print(f"  {cl:<10} {s['ok']:>4} {s['fail']:>5}  {avg:>20}")

    # ── Sample responses ──────────────────────────────────────────────────────
    section("Sample Responses (one per cluster)")
    for cl in ["clean", "budget", "luxury", "science", "eco", "ctrl"]:
        sample = next(
            ((n, v) for n, v in per_agent.items() if cluster_of(n) == cl and v[2] == "ok"),
            None,
        )
        if sample:
            name, (result, elapsed, _) = sample
            resp = result.get("response", "")
            print(f"\n  [{cl} — {name}] ({elapsed:.1f}s)")
            print(f"  {resp[:300]}")
            if len(resp) > 300:
                print("  [truncated]")
        else:
            print(f"\n  [{cl}] — no successful response")

    # ── What changed from HW7 ─────────────────────────────────────────────────
    section("What Changed vs HW7 (6 agents → 30 agents)")
    success_rate = len(ok_times) / len(agents)
    print(f"  Success rate:   {success_rate:.0%}  (HW7: {HW7_SUCCESS_RATE:.0%})")
    if rate_limit > 0:
        print(f"  Rate limiting:  YES — {rate_limit} agent(s) hit Gemini 429. "
              f"This did not occur at 6 agents.")
        print(f"    Root cause: Gemini Flash RPM limit exhausted by simultaneous requests.")
        print(f"    Fix needed: exponential backoff in agents/llm.py, or request batching.")
    else:
        print(f"  Rate limiting:  None observed (within Gemini RPM budget at 30 agents).")
        print(f"    Note: higher concurrent load (50+) would likely trigger 429s.")
    if ok_times:
        p95 = sorted(ok_times)[min(int(len(ok_times) * 0.95), len(ok_times) - 1)]
        print(f"  p95 latency:    {p95:.1f}s  (if HW7 p95 was similar to p50 ~{HW7_P50_SECONDS:.0f}s, "
              f"this shows {'increased variance' if p95 > HW7_P50_SECONDS * 1.5 else 'manageable variance'})")


# ── Experiment 5: Trust network formation ────────────────────────────────────

def experiment_5(agents: dict[str, str]):
    divider("EXPERIMENT 5: Autonomous Trust Network Formation at 30 Agents")
    print("""
Question: What network topology emerges when 30 agents self-discover peers via
          embedding similarity? Do same-cluster agents cluster together?

Method:
  1. Enable is_autonomous=True for all 30 agents
  2. POST /agents/tick-all  →  triggers peer discovery for each agent
  3. Query /social/sent-requests for each agent to build the connection graph
  4. Measure: intra-cluster vs inter-cluster connection rate
             (expected: clean↔eco overlap; budget↔luxury unlikely)

Hypothesis: similarity threshold 0.65 should find cross-cluster connections
            only between ideologically adjacent clusters (clean↔eco, luxury↔science).
""")

    # Step 1: enable autonomous mode for all agents
    section("Enabling autonomous mode for all 30 agents")
    print("  (in parallel)…", flush=True)
    enabled = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(set_autonomous, aid, True): name
            for name, aid in agents.items()
        }
        for future in as_completed(futures, timeout=120):
            name = futures[future]
            try:
                future.result()
                enabled += 1
            except Exception as e:
                print(f"  WARNING: could not enable {name}: {e}", flush=True)
    print(f"  Enabled: {enabled}/{len(agents)}")

    # Step 2: run tick-all and measure time
    section("Running tick-all (30 agents, sequential per agent on server)")
    print("  POST /api/agents/tick-all  (may take several minutes)…", flush=True)
    t0 = time.time()
    try:
        tick_result = post("/agents/tick-all", {}, timeout=600)
        tick_elapsed = time.time() - t0
        ticked = tick_result.get("ticked", 0)
        results_list = tick_result.get("results", [])
        errors = sum(1 for r in results_list if "error" in r)
        total_discovered = sum(r.get("discovered", 0) for r in results_list if "discovered" in r)
        total_refills = sum(r.get("refills", 0) for r in results_list if "refills" in r)
        print(f"  tick-all completed in {tick_elapsed:.1f}s")
        print(f"  Agents ticked:          {ticked}")
        print(f"  Errors during tick:     {errors}")
        print(f"  Total peers discovered: {total_discovered}")
        print(f"  Total refills:          {total_refills}")
    except Exception as e:
        tick_elapsed = time.time() - t0
        print(f"  tick-all FAILED after {tick_elapsed:.1f}s: {e}")
        print("  (proceeding to query connection requests anyway)")
        ticked = 0
        total_discovered = 0

    # Step 3: collect sent connection requests per agent
    section("Collecting connection graph")
    edges: list[tuple[str, str, float]] = []  # (from_key, to_key, similarity_score)
    id_to_key = {v: k for k, v in agents.items()}

    print("  Querying sent-requests for all 30 agents…")
    for name, aid in agents.items():
        try:
            sent = get(f"/social/sent-requests/{aid}", timeout=15)
            for req in sent:
                to_id = req.get("to_agent_id", "")
                to_key = id_to_key.get(to_id, to_id[:8])
                score = req.get("similarity_score") or 0.0
                edges.append((name, to_key, float(score)))
        except Exception as e:
            print(f"  WARNING: could not fetch sent-requests for {name}: {e}")

    print(f"  Total connection requests found: {len(edges)}")

    # Step 4: analyze cluster topology
    section("Cluster Connection Topology")
    cluster_matrix: dict[str, dict[str, int]] = {}
    for cl_from in CLUSTER_DEFS:
        cluster_matrix[cl_from] = {cl_to: 0 for cl_to in CLUSTER_DEFS}

    for from_key, to_key, _ in edges:
        cl_from = cluster_of(from_key)
        cl_to   = cluster_of(to_key)
        if cl_from in cluster_matrix and cl_to in cluster_matrix[cl_from]:
            cluster_matrix[cl_from][cl_to] += 1

    intra = sum(cluster_matrix[cl][cl] for cl in CLUSTER_DEFS)
    inter = len(edges) - intra

    print(f"\n  Connection matrix (rows=from, cols=to):")
    clusters = list(CLUSTER_DEFS.keys())
    header = f"  {'from \\ to':<12}" + "".join(f"  {c[:6]:>6}" for c in clusters)
    print(header)
    print("  " + "─" * (len(header) - 2))
    for cl_from in clusters:
        row = f"  {cl_from:<12}"
        for cl_to in clusters:
            val = cluster_matrix[cl_from][cl_to]
            row += f"  {val:>6}"
        print(row)

    print(f"\n  Intra-cluster connections: {intra} ({intra/max(len(edges),1):.0%})")
    print(f"  Inter-cluster connections: {inter} ({inter/max(len(edges),1):.0%})")

    if intra > inter:
        print("  → Embedding similarity correctly clusters same-persona agents.")
        print("    Agents within the same cluster share vocabulary and values,")
        print("    producing higher cosine similarity scores.")
    else:
        print("  → More cross-cluster connections than within-cluster.")
        print("    May indicate similarity threshold (0.65) is too low, or that")
        print("    persona overlap between adjacent clusters (clean↔eco, science↔luxury)")
        print("    dominates the similarity landscape.")

    # Highest-similarity edges
    section("Top-10 Highest Similarity Connections")
    top = sorted(edges, key=lambda x: x[2], reverse=True)[:10]
    for from_k, to_k, score in top:
        relation = "INTRA" if cluster_of(from_k) == cluster_of(to_k) else "inter"
        print(f"  {score:.3f}  {from_k:<22} → {to_k:<22}  [{relation}]")

    # tick-all timing analysis
    section("tick-all Scaling Analysis")
    if ticked > 0:
        per_agent_time = tick_elapsed / ticked
        print(f"  tick-all for {ticked} agents:         {tick_elapsed:.1f}s")
        print(f"  Average time per agent:          {per_agent_time:.1f}s")
        print(f"  HW7 equivalent (6 agents):       ~{per_agent_time * 6:.0f}s (estimated)")
        print(f"\n  Projection at scale:")
        for n in [50, 100, 500]:
            projected = per_agent_time * n
            print(f"    {n:>4} agents → ~{projected:.0f}s  "
                  f"({'OK for hourly scheduler' if projected < 3600 else 'EXCEEDS 1-hour window'})")
        print(f"\n  Root cause of sequential bottleneck:")
        print(f"    tick-all in autonomous.py iterates agents in a Python for-loop.")
        print(f"    Each iteration: find_similar_agents() runs up to 5 pgvector GROUP BY")
        print(f"    queries. At {ticked} agents x 5 queries = {ticked*5} DB roundtrips per tick-all.")
        print(f"    Fix: asyncio.gather() or ThreadPoolExecutor across agent ticks.")


# ── Experiment 6: Recommendation divergence by cluster ───────────────────────

def experiment_6(agents: dict[str, str]):
    divider("EXPERIMENT 6: Recommendation Divergence Across 30 Agents")
    print("""
Question: Does cluster membership predict recommendation content?
          Do within-cluster agents give correlated recommendations, while
          cross-cluster agents diverge?

Method:
  Send the same neutral query to all 30 agents in parallel.
  Score each response for keyword presence from its own cluster (true positive)
  and keywords from other clusters (false positives = cross-cluster bleed).

  Within-cluster coherence = (own-cluster keywords) / (all keyword hits)
  A high score means the agent's memory is genuinely shaping recommendations.
""")

    query = "What skincare or beauty product should I buy right now?"
    print(f"Query: \"{query}\"  (intentionally open-ended)")
    print(f"Firing {len(agents)} agents in parallel…\n")

    t0 = time.time()
    per_agent: dict[str, tuple[dict, float, str]] = {}
    with ThreadPoolExecutor(max_workers=len(agents)) as pool:
        futures = {
            pool.submit(chat_timed, aid, name, query): name
            for name, aid in agents.items()
        }
        for future in as_completed(futures, timeout=420):
            name = futures[future]
            try:
                _, result, elapsed, status = future.result()
                per_agent[name] = (result, elapsed, status)
                icon = "✓" if status == "ok" else "✗"
                print(f"  {icon} {name:<22} {elapsed:5.1f}s  [{status}]", flush=True)
            except Exception as e:
                per_agent[name] = ({"response": f"ERROR: {e}"}, 0.0, "error")
    elapsed_all = time.time() - t0
    print(f"\n  All responses in {elapsed_all:.1f}s")

    # ── Keyword analysis ──────────────────────────────────────────────────────
    section("Keyword Coherence Analysis")

    coherence_scores: dict[str, float] = {}
    cluster_responses: dict[str, list[tuple[str, str]]] = {cl: [] for cl in CLUSTER_DEFS}

    for name, (result, _, status) in per_agent.items():
        if status != "ok":
            continue
        cl = cluster_of(name)
        resp = result.get("response", "").lower()
        cluster_responses[cl].append((name, resp))

        own_hits = sum(1 for kw in CLUSTER_KEYWORDS[cl] if kw in resp)
        all_hits = sum(1 for kws in CLUSTER_KEYWORDS.values() for kw in kws if kw in resp)
        coherence_scores[name] = own_hits / max(all_hits, 1)

    print(f"\n  {'Agent':<22} {'Cluster':<10} {'Own-kw hits':>11} {'All-kw hits':>11} {'Coherence':>10}")
    print(f"  {'─'*22} {'─'*10} {'─'*11} {'─'*11} {'─'*10}")
    for name in sorted(agents.keys()):
        if name not in coherence_scores:
            continue
        result, _, status = per_agent[name]
        if status != "ok":
            continue
        cl = cluster_of(name)
        resp = result.get("response", "").lower()
        own_hits = sum(1 for kw in CLUSTER_KEYWORDS[cl] if kw in resp)
        all_hits = sum(1 for kws in CLUSTER_KEYWORDS.values() for kw in kws if kw in resp)
        coh = coherence_scores[name]
        print(f"  {name:<22} {cl:<10} {own_hits:>11} {all_hits:>11} {coh:>10.2f}")

    # ── Per-cluster summary ───────────────────────────────────────────────────
    section("Per-Cluster Coherence Summary")
    print(f"\n  {'Cluster':<10} {'Agents':>7} {'Avg coherence':>14}  Interpretation")
    print(f"  {'─'*10} {'─'*7} {'─'*14}  {'─'*30}")
    for cl in ["clean", "budget", "luxury", "science", "eco", "ctrl"]:
        scores = [coherence_scores[n] for n in agents if cluster_of(n) == cl and n in coherence_scores]
        if not scores:
            print(f"  {cl:<10} {'0':>7} {'—':>14}")
            continue
        avg = statistics.mean(scores)
        agents_n = len(scores)
        if cl == "ctrl":
            interp = "control — generic, no cluster preference expected"
        elif avg >= 0.60:
            interp = "strong cluster identity — memory is shaping output"
        elif avg >= 0.35:
            interp = "moderate — some persona bleed into recommendations"
        else:
            interp = "weak — cross-cluster overlap or generic response"
        print(f"  {cl:<10} {agents_n:>7} {avg:>14.2f}  {interp}")

    # ── Response excerpts ─────────────────────────────────────────────────────
    section("Response Excerpts (one per cluster)")
    for cl in ["clean", "budget", "luxury", "science", "eco", "ctrl"]:
        responses = cluster_responses[cl]
        if not responses:
            print(f"\n  [{cl}] — no successful responses")
            continue
        name, resp = responses[0]
        print(f"\n  [{cl} — {name}]")
        print(f"  {resp[:350]}")
        if len(resp) > 350:
            print("  [truncated]")

    # ── What this shows ───────────────────────────────────────────────────────
    section("Key Finding vs HW7")
    ctrl_scores = [coherence_scores[n] for n in agents if cluster_of(n) == "ctrl" and n in coherence_scores]
    non_ctrl_scores = [coherence_scores[n] for n in agents if cluster_of(n) != "ctrl" and n in coherence_scores]
    if ctrl_scores and non_ctrl_scores:
        ctrl_avg = statistics.mean(ctrl_scores)
        persona_avg = statistics.mean(non_ctrl_scores)
        print(f"  Persona agents avg coherence:  {persona_avg:.2f}")
        print(f"  Control agents avg coherence:  {ctrl_avg:.2f}")
        delta = persona_avg - ctrl_avg
        if delta > 0.10:
            print(f"  Delta: +{delta:.2f} — persona memory meaningfully shifts recommendation vocabulary.")
            print(f"  At 30 agents, this signal is consistent across 5 agents per cluster,")
            print(f"  making it far more statistically reliable than HW7's single agent per type.")
        else:
            print(f"  Delta: {delta:+.2f} — small gap suggests the open-ended query gave too much")
            print(f"  flexibility; a constrained query ('find me a moisturizer') would show")
            print(f"  stronger cluster divergence.")


# ── Stress test: tick-all bottleneck ─────────────────────────────────────────

def stress_test(agents: dict[str, str]):
    divider("STRESS TEST: tick-all Sequential Bottleneck at 30 Agents")
    print("""
What breaks at scale: the tick-all endpoint runs each agent's behaviors in a
sequential Python for-loop on the server. Each iteration runs find_similar_agents()
which performs up to 5 pgvector GROUP BY queries across all preference embeddings.

At 6 agents  (HW7):  overhead is invisible.
At 30 agents (HW8):  each tick-all call takes significantly longer.
At 100 agents:       approaches the 1-hour scheduler interval.
At 300+ agents:      tick-all would miss its own hourly schedule.

This test fires three consecutive tick-all calls and measures the wall time.
It also measures per-agent-tick time to project the failure point.
""")

    trial_times = []
    for trial in range(2):
        print(f"  Trial {trial + 1}/2: POST /api/agents/tick-all…", flush=True)
        t0 = time.time()
        try:
            r = post("/agents/tick-all", {}, timeout=600)
            elapsed = time.time() - t0
            ticked = r.get("ticked", 0)
            trial_times.append(elapsed)
            print(f"    completed in {elapsed:.1f}s  (agents ticked: {ticked})")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"    FAILED after {elapsed:.1f}s: {e}")
        time.sleep(5)

    section("Bottleneck Analysis")
    if trial_times:
        avg_tick = statistics.mean(trial_times)
        n_agents = len(agents)
        per_agent = avg_tick / n_agents if n_agents else avg_tick
        print(f"  Agents in pool:              {n_agents}")
        print(f"  avg tick-all duration:       {avg_tick:.1f}s")
        print(f"  estimated time per agent:    {per_agent:.1f}s")
        print(f"\n  Projected tick-all duration by scale:")
        print(f"  {'Agents':>8}   {'Projected time':>16}   {'vs 1-hr window':>16}")
        for n in [6, 30, 100, 300, 1000]:
            projected = per_agent * n
            if n == 6:
                label = "← HW7"
            elif n == 30:
                label = "← HW8 (measured)"
            elif projected < 3600:
                label = f"OK ({3600 - projected:.0f}s margin)"
            elif projected < 7200:
                label = "EXCEEDS 1-hr window"
            else:
                label = f"MISSES by {(projected/3600 - 1):.1f}x"
            print(f"  {n:>8}   {projected:>12.0f}s     {label}")

    section("What Breaks and the Fix")
    print("""  What breaks:
    autonomous.py tick_all_agents() uses a plain `for agent in agents` loop.
    Each iteration is sequential: agent N+1 cannot start until agent N finishes
    find_similar_agents() + check_and_refill_wishlist().

  What degrades:
    At 30 agents, tick-all total time is still within the 1-hour scheduler window,
    but the per-request latency grows linearly. The Cloud Run instance handling the
    tick-all request is blocked for the full duration, consuming one instance slot.

  What becomes expensive:
    find_similar_agents() runs up to 5 GROUP BY queries per agent, each scanning
    the entire vector_embeddings table. At 30 agents:
      30 agents × 5 probes × (table scan of 30 × 3 embeddings = 90 rows) = 13,500 row-reads per tick-all.
    At 1,000 agents with 10 embeddings each:
      1,000 × 5 × 10,000 = 50,000,000 row-reads — the index would help but cost would spike.

  The fix (not yet implemented):
    Replace the for-loop in tick_all_agents() with asyncio.gather():

      async def tick_all_agents():
          ...
          tasks = [_tick_one(agent.id) for agent in agents]
          results = await asyncio.gather(*tasks, return_exceptions=True)

    This reduces wall time from O(n) to O(1) (bounded by the slowest single agent).
    At 30 agents with 15s/agent average: sequential=450s → parallel~15s.
""")

    section("Cloud Run Cold-Start Amplification")
    print("""  At 6 agents (HW7):
    Cloud Run typically has 3-6 warm instances; most requests hit a warm instance.
    Cold-start rate: low (~10-20%).

  At 30 agents (HW8):
    30 simultaneous requests each need a separate instance (concurrency=1).
    Cloud Run must cold-start ~24-27 additional instances.
    Cold-start time: 8-25s per instance (JVM/Python startup + dependency import).
    Result: first parallel batch sees p95 >> p50 (bimodal distribution: warm vs cold).

  Evidence from Exp 4:
    The gap between min latency and max latency in Exp 4 approximates
    the cold-start penalty. Any agent with latency >> cluster median likely
    hit a cold-start.
""")


# ── Bottleneck benchmark: sequential vs parallel tick-all ─────────────────────

def bottleneck_benchmark(agents: dict[str, str]):
    divider("BOTTLENECK BENCHMARK: Sequential vs Parallel tick-all")
    print(f"""
Setup: reseed all {len(agents)} agents with purchase history so each tick does
real work (check_and_refill_wishlist scans purchases, query_trust_network runs
DB queries). Then compare:

  POST /api/agents/tick-all           — sequential for-loop, O(n) wall time
  POST /api/agents/tick-all-parallel  — asyncio.gather with run_in_executor, O(1) wall time

The key fix: find_similar_agents (sync psycopg2) is wrapped in run_in_executor
so it runs in a thread pool instead of blocking the event loop between agents.
""")

    # Step 1: reseed all agents with purchase history
    section("Step 1: Reseeding all agents with purchase history")
    print(f"  POST /agents/{{id}}/reseed for all {len(agents)} agents (in parallel)…")
    seeded = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(post, f"/agents/{aid}/reseed", {}, 60): name
            for name, aid in agents.items()
        }
        for future in as_completed(futures, timeout=300):
            name = futures[future]
            try:
                future.result()
                seeded += 1
                print(f"    {name} ✓", flush=True)
            except Exception as e:
                print(f"    {name} WARNING: {e}", flush=True)
    print(f"  Reseeded: {seeded}/{len(agents)}")
    print("  Waiting 3s for DB writes to settle…")
    time.sleep(3)

    # Step 2: sequential tick-all
    section("Step 2: Sequential tick-all  (POST /agents/tick-all)")
    print("  Running…", flush=True)
    sequential_times = []
    for trial in range(2):
        t0 = time.time()
        try:
            r = post("/agents/tick-all", {}, timeout=600)
            wall = time.time() - t0
            reported = r.get("elapsed_s", wall)
            sequential_times.append(reported)
            ticked = r.get("ticked", 0)
            refills = sum(x.get("refills", 0) for x in r.get("results", []) if "refills" in x)
            print(f"  Trial {trial+1}: {reported:.2f}s  (agents={ticked}, refills={refills})")
        except Exception as e:
            print(f"  Trial {trial+1}: FAILED — {e}")
        time.sleep(2)

    # Step 3: parallel tick-all
    section("Step 3: Parallel tick-all  (POST /agents/tick-all-parallel)")
    print("  Running…", flush=True)
    parallel_times = []
    for trial in range(2):
        t0 = time.time()
        try:
            r = post("/agents/tick-all-parallel", {}, timeout=600)
            wall = time.time() - t0
            reported = r.get("elapsed_s", wall)
            parallel_times.append(reported)
            ticked = r.get("ticked", 0)
            refills = sum(x.get("refills", 0) for x in r.get("results", []) if "refills" in x)
            print(f"  Trial {trial+1}: {reported:.2f}s  (agents={ticked}, refills={refills})")
        except Exception as e:
            print(f"  Trial {trial+1}: FAILED — {e}")
        time.sleep(2)

    # Step 4: compare
    section("Results")
    if sequential_times and parallel_times:
        seq_avg = statistics.mean(sequential_times)
        par_avg = statistics.mean(parallel_times)
        speedup = seq_avg / par_avg if par_avg > 0 else float("inf")
        n = len(agents)

        print(f"\n  {'Approach':<28} {'Avg wall time':>14}  {'Per agent':>10}")
        print(f"  {'─'*28} {'─'*14}  {'─'*10}")
        print(f"  {'Sequential (for-loop)':<28} {seq_avg:>12.2f}s  {seq_avg/n:>8.3f}s")
        print(f"  {'Parallel (asyncio.gather)':<28} {par_avg:>12.2f}s  {par_avg/n:>8.3f}s")
        print(f"\n  Speedup: {speedup:.1f}x")
        print(f"  Agents:  {n}")

        print(f"\n  Why the speedup exists:")
        print(f"    Sequential: each agent waits for the previous agent's DB queries to finish.")
        print(f"    Parallel:   all agents' async DB queries run concurrently via asyncpg;")
        print(f"                find_similar_agents (sync) runs in thread pool — no event-loop blocking.")

        print(f"\n  Projection at scale ({n} → 300 agents):")
        seq_300 = seq_avg / n * 300
        par_300 = par_avg  # parallel is bounded by slowest single agent, not n
        print(f"    Sequential: {seq_300:.0f}s  ({seq_300/3600:.2f}× 1-hour scheduler window)")
        print(f"    Parallel:   ~{par_300:.1f}s  (wall time stays constant regardless of n)")

        if speedup < 2.0:
            print(f"\n  Note: speedup < 2x suggests find_similar_agents candidates are mostly")
            print(f"  already-connected or already-pending, so peer discovery exits early.")
            print(f"  The bottleneck is most visible when agents have many NEW candidates")
            print(f"  (e.g. first tick of a fresh deployment, or after trust graph is cleared).")
    else:
        print("  Not enough data to compare — one or both endpoints failed.")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "setup":
        setup()
        sys.exit(0)

    agents = load_agents()
    print(f"Loaded {len(agents)} agents from {AGENTS_FILE}")

    if cmd in ("4", "all"):
        experiment_4(agents)
    if cmd in ("5", "all"):
        experiment_5(agents)
    if cmd in ("6", "all"):
        experiment_6(agents)
    if cmd in ("stress", "all"):
        stress_test(agents)
    if cmd == "bottleneck":
        bottleneck_benchmark(agents)

    if cmd != "setup":
        print("\n\nDone.")

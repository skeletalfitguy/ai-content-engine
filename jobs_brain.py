import os
import sys
import json
import time
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("❌ Missing GEMINI_API_KEY inside your .env file!")

MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"]
BASE = "https://generativelanguage.googleapis.com/v1beta"
RAW_FILE = "jobs_raw.json"
PACK_FILE = "jobs_pack.json"

SYSTEM = """You are the career agent for Muhammad Anas — an early-career copywriter & creative
strategist. Pakistan-based, fully remote, Upwork Rising Talent. He is empty-handed right now, so
ANY relevant copywriting / content / email / marketing / creative-strategy role — including
entry-level and internships — is a win. Rank generously and encourage.

His two positioning angles (pick the better-fitting resume per job):
A) "Creative Strategy" — Facebook/Meta ads copywriter & creative strategist: FB ad copy, VSL scripts,
   15-sec short-form video ad scripts (UGC, hook-reveal, pattern-interrupt), static ad design, AI
   video ad production (Veo3/Kling/Seedance), creative strategy (ad diagnosis, hook analysis,
   CTR/CVR, offer positioning). NOT a media buyer, NOT a technical ads manager.
B) "Copywriting & Email" — copywriter & email marketing specialist: email sequences, cold email
   (Instantly/Manyreach/GMass), Klaviyo, landing pages, sales pages, website copy, direct-response,
   cold email infrastructure (domains/DNS/warmup).
Trained under Shahzad Khan (6-Figures Copywriting Program, $40M+ client sales). Professional English.

Return ONLY valid JSON. No markdown, no text outside the JSON. Never invent details about the job
that aren't in what you're given."""

PROMPT = """Here are today's jobs (id + title + company + location + short description):

{data}

For EACH job return an analysis object. Return JSON exactly:
{{"jobs": [
  {{
    "id": <the id>,
    "fit_score": <0-100 how well it matches Anas>,
    "match": "strong" | "stretch",     // strong = directly needs his copy/email/content/ad/creative skills; stretch = adjacent or a bit senior but still worth applying
    "resume": "Creative Strategy" | "Copywriting & Email",   // whichever fits better
    "why": "one honest sentence on why it fits (or why it's a stretch)",
    "proposal_opener": "1-2 line opening line for his application, in a punchy direct-response voice, no fluff, no 'Dear Hiring Manager'",
    "flags": "short heads-up if any (e.g. 'senior role - position as eager junior', 'needs German') or empty string",
    "summary": "2 plain sentences on what the role actually is"
  }}
]}}
Include every id. Be encouraging but honest about stretches."""


def call_gemini(prompt, retries=3):
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "responseMimeType": "application/json",
                             "maxOutputTokens": 24576},
    }
    for model in MODELS:
        url = f"{BASE}/models/{model}:generateContent?key={GEMINI_API_KEY}"
        for attempt in range(retries):
            r = requests.post(url, json=payload, timeout=150)
            if r.status_code == 200:
                print(f"  ✓ answered by {model}")
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            if r.status_code in (429, 500, 502, 503, 504):
                wait = 10 * (attempt + 1)
                print(f"  ⏳ {model} busy ({r.status_code}), waiting {wait}s...")
                time.sleep(wait); continue
            raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
        print(f"  ↪ {model} unavailable, falling back...")
    raise RuntimeError("All Gemini models failed after retries")


def main():
    jobs = json.load(open(RAW_FILE, encoding="utf-8"))
    if not jobs:
        print("😴 No new jobs today — keeping the last pack.")
        return

    compact = [{"id": i, "title": j["title"], "company": j["company"],
                "location": j["location"], "description": j["description"][:350]}
               for i, j in enumerate(jobs)]
    print(f"🧠 Scoring {len(jobs)} jobs against Anas's resumes...\n")
    analysis = json.loads(call_gemini(PROMPT.format(data=json.dumps(compact, ensure_ascii=False))))

    by_id = {a["id"]: a for a in analysis.get("jobs", [])}
    enriched = []
    for i, j in enumerate(jobs):
        a = by_id.get(i, {})
        enriched.append({**j,
                         "fit_score": a.get("fit_score", 50), "match": a.get("match", "stretch"),
                         "resume": a.get("resume", "Copywriting & Email"), "why": a.get("why", ""),
                         "proposal_opener": a.get("proposal_opener", ""), "flags": a.get("flags", ""),
                         "summary": a.get("summary", j["description"][:200])})
    # best match first (what he actually applies to); the recency filter already
    # guarantees every job is fresh, and the dashboard flags brand-new ones.
    enriched.sort(key=lambda x: (x.get("fit_score", 0), x.get("date", "")), reverse=True)

    pack = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "jobs": enriched}
    with open(PACK_FILE, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=4, ensure_ascii=False)

    # archive for openable history days
    os.makedirs("history", exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(f"history/jobs_{day}.json", "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=4, ensure_ascii=False)
    try:
        idx = json.load(open("history/index.json", encoding="utf-8"))
    except Exception:
        idx = {}
    idx.setdefault("jobs", [])
    if day not in idx["jobs"]:
        idx["jobs"].append(day); idx["jobs"].sort()
    json.dump(idx, open("history/index.json", "w", encoding="utf-8"), indent=2)

    strong = sum(1 for j in enriched if j["match"] == "strong")
    print("=" * 60)
    for j in enriched[:10]:
        print(f"  [{j['fit_score']:>3}] {j['match']:<7} {j['title'][:45]}  → {j['resume']}")
    print(f"\n✅ {len(enriched)} jobs ranked ({strong} strong) → {PACK_FILE}")


if __name__ == "__main__":
    main()

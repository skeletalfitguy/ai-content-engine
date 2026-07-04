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

MODEL = "gemini-flash-latest"   # free tier, auto-tracks newest Flash
BASE = "https://generativelanguage.googleapis.com/v1beta"
NICHE = "faceless AI FITNESS YouTube Shorts (the '3D anatomy / what happens inside your body when you exercise' format)"

SYSTEM = f"""You are a viral short-form strategist for a {NICHE} channel.
You get real YouTube outlier data (fitness shorts that got far more views than
their channel's subscriber count). Turn it into a daily content brief.
In THIS niche the two strongest patterns are:
  1) "[Exercise A] VS [Exercise B] — see what happens inside your body"
  2) "What happens if you do [exercise] every day"
Reward those angles. Keep everything strictly FITNESS (workouts, muscles, gym,
running, form) — NO diet fads, NO pregnancy, NO random facts.
Return ONLY valid JSON. No markdown fences, no commentary outside the JSON."""

PROMPT = """Today's real fitness outliers (title = hook; ratio = views / subs; vs/everyday flags shown):

{data}

Return JSON with EXACTLY these keys:

"scored_topics": array of up to 8 objects, ranked best first:
  {{"topic": "the video idea for OUR channel", "score": 0-100 virality score,
    "angle": "VS" | "everyday" | "single-exercise",
    "why": "1 sentence on why it will retain in the first 2 seconds"}}

"winning_templates": array of up to 4:
  {{"template": "reusable hook pattern with ___ blanks",
    "why_it_works": "1 sentence trigger", "proof": "highest-ratio real example"}}

"todays_hooks": array of 10 BRAND-NEW fitness hook titles for OUR channel using the
winning templates but fresh exercises/comparisons not in the data. Punchy, <70 chars.

"shorts_scripts": array of 3 ready-to-produce scripts:
  {{"hook": "exact first line / on-screen text (lands in 2 seconds)",
    "beats": ["3-5 short narration beats"],
    "payoff": "the surprising fact that makes people rewatch",
    "visual_note": "what the 3D anatomy shows"}}
"""


def load_outliers(path="youtube_outliers.json"):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    lines = []
    for o in data:
        flags = []
        if o.get("is_vs"):
            flags.append("VS")
        if o.get("is_everyday"):
            flags.append("EVERYDAY")
        tag = f" [{','.join(flags)}]" if flags else ""
        lines.append(f"- [{o['ratio']}x] {o['title']}{tag}")
    return "\n".join(lines) if lines else "(no new outliers today)"


def call_gemini(prompt, retries=3):
    url = f"{BASE}/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"},
    }
    for attempt in range(retries):
        r = requests.post(url, json=payload, timeout=90)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        if r.status_code == 429:  # rate limit — respect RPM, wait and retry
            wait = 6 * (attempt + 1)
            print(f"  ⏳ rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
    raise RuntimeError("Gemini failed after retries")


def main():
    data = load_outliers()
    print("🧠 Sending fitness outliers to Gemini...\n")
    raw = call_gemini(PROMPT.format(data=data))
    pack = json.loads(raw)
    pack["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open("content_pack.json", "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=4, ensure_ascii=False)

    print("=" * 60)
    print("🏆 TOP SCORED TOPICS")
    for t in pack.get("scored_topics", [])[:8]:
        print(f"  [{t['score']:>3}] ({t['angle']}) {t['topic']}")
    print("\n✨ FRESH HOOKS")
    for h in pack.get("todays_hooks", []):
        print(f"  - {h}")
    print(f"\n🎬 {len(pack.get('shorts_scripts', []))} scripts · saved to content_pack.json")


if __name__ == "__main__":
    main()

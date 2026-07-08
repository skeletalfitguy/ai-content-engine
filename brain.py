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

MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"]  # fallback chain
BASE = "https://generativelanguage.googleapis.com/v1beta"
NICHE = "faceless AI FITNESS YouTube Shorts (the '3D anatomy / what happens inside your body when you exercise' format)"

SYSTEM = f"""You are a viral short-form strategist AND scriptwriter for a {NICHE} channel.
You get real YouTube outlier data (fitness shorts that beat their channel's subscriber count).
Turn it into a daily content pack where EACH idea is fully self-contained: the topic, its hook,
and a COMPLETE word-for-word script that fills a 30-45 second Short.
Strongest patterns in this niche: (1) "[Exercise A] VS [Exercise B] — what happens inside your body",
(2) "What happens if you do [exercise] every day". Reward those.
Keep everything strictly FITNESS. Return ONLY valid JSON, no markdown, no text outside the JSON."""

PROMPT = """Today's real fitness outliers (title = proven hook; ratio = views/subs; flags shown):

{data}

Return JSON with EXACTLY these keys:

"ideas": array of 6 self-contained video ideas, ranked best first. Each object:
  {{
    "topic": "short idea name for our channel",
    "score": 0-100 virality score,
    "angle": "VS" | "everyday" | "single-exercise",
    "why": "1 sentence: why it stops the scroll in 2 seconds",
    "hook": "the EXACT first spoken line + on-screen text (must land in 2 seconds)",
    "title": "the YouTube title to publish (<70 chars)",
    "script_beats": [
        "5 to 7 FULL word-for-word narration sentences the voiceover actually says, in order, that together run ~30-45 seconds"
    ],
    "payoff": "the final surprising line that makes people rewatch/share",
    "cta": "a short call to action (e.g. 'Follow for the other half of your body')",
    "visual_note": "what the 3D anatomy shows on screen during this",
    "inspired_by_title": "copy the real outlier title above that this idea is modeled on (the title text only, WITHOUT the [VS]/[EVERYDAY] tag)"
  }}

"winning_templates": array of up to 3:
  {{"template": "reusable hook pattern with ___ blanks",
    "why_it_works": "1 sentence trigger", "proof": "highest-ratio real example"}}
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
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"},
    }
    for model in MODELS:  # try each model; fall back if one is overloaded
        url = f"{BASE}/models/{model}:generateContent?key={GEMINI_API_KEY}"
        for attempt in range(retries):
            r = requests.post(url, json=payload, timeout=120)
            if r.status_code == 200:
                print(f"  ✓ answered by {model}")
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            if r.status_code in (429, 500, 502, 503, 504):
                wait = 10 * (attempt + 1)
                print(f"  ⏳ {model} busy ({r.status_code}), waiting {wait}s...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
        print(f"  ↪ {model} unavailable, falling back...")
    raise RuntimeError("All Gemini models failed after retries")


def main():
    with open("youtube_outliers.json", encoding="utf-8") as f:
        raw = json.load(f)
    if not raw:
        print("😴 No new outliers today — keeping the last good brief on the dashboard.")
        return

    data = load_outliers()
    print("🧠 Sending fitness outliers to Gemini...\n")
    pack = json.loads(call_gemini(PROMPT.format(data=data)))
    pack["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open("content_pack.json", "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=4, ensure_ascii=False)

    # archive today's brief so past days stay openable on the dashboard
    os.makedirs("history", exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(f"history/fit_{day}.json", "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=4, ensure_ascii=False)
    try:
        with open("history/index.json", encoding="utf-8") as f:
            idx = json.load(f)
    except Exception:
        idx = {}
    idx.setdefault("fit", [])
    if day not in idx["fit"]:
        idx["fit"].append(day)
        idx["fit"].sort()
    with open("history/index.json", "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)

    print("=" * 60)
    print("🎯 TODAY'S IDEAS (each with full script)")
    for i in pack.get("ideas", []):
        print(f"  [{i.get('score','?'):>3}] ({i.get('angle','?')}) {i.get('topic','')}")
        print(f"        hook: {i.get('hook','')[:70]}")
        print(f"        script beats: {len(i.get('script_beats', []))}")
    print(f"\n✅ {len(pack.get('ideas', []))} full ideas saved to content_pack.json")


if __name__ == "__main__":
    main()

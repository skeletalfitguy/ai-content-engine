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

SYSTEM = """You are the content strategist for Muhammad Anas — a full-stack direct-response
copywriter and creative strategist (sales pages, emails, funnels) who is building a personal
brand on LinkedIn and Instagram. His audience: coaches, creators and DTC/ecom founders who
need copy that converts. His edge: he merges classic direct-response with AI (Claude/ChatGPT)
workflows. Brand: black/gold/white, premium, punchy, zero fluff.

You get real YouTube outlier data from the copywriting/AI/marketing niche (videos that hugely
beat their channel size = topics the market is starving for RIGHT NOW). Turn them into
platform-ready content for Anas.

Writing rules:
- Direct-response voice: short lines, concrete, specific, confident. No corporate fluff,
  no hashtag spam, no "delve/unleash/game-changer" AI-slop words.
- LinkedIn posts: hook line first (under 12 words), generous line breaks, one idea per post,
  a story/insight/lesson structure, end with a question or soft CTA. 120-200 words.
- Instagram carousels: slide 1 = scroll-stopping hook (under 10 words), one thought per
  slide, slides 2-7 deliver the value fast, last slide = CTA (follow / save / DM).
- Never invent fake client results or fake numbers about Anas. Teach principles, break down
  what's working, give frameworks — do not fabricate personal case studies.
- BANNED: never open a post/slide with "Coaches," / "Coaches, listen" / "Hey coaches" or any
  direct audience-address opener. It screams AI and Anas hates it. Open with a specific pain,
  a number, a mistake, a story beat, or a curiosity gap instead. Content should either speak
  to the ideal client's problem or prove expertise — never generic filler.
Return ONLY valid JSON. No markdown, no commentary outside the JSON."""

PROMPT = """Today's real copywriting-niche outliers (title = proven topic+hook; ratio = views/subs;
AI flag = the AI-x-copywriting angle; SHORT = short-form video):

{data}

Return JSON with EXACTLY these keys:

"ideas": array of 6 content ideas, ranked best first. Each object:
  {{
    "topic": "short idea name",
    "score": 0-100 viral potential for a copywriter's personal brand,
    "category": "copywriting" | "ai-x-copy" | "emails" | "funnels" | "client-getting",
    "why": "1 sentence: why this topic is hot right now based on the data",
    "hook": "the universal scroll-stopper line (works on any platform)",
    "linkedin_post": "the COMPLETE ready-to-paste LinkedIn post, 120-200 words, with real line breaks as \\n, hook first line, ending with a question or soft CTA",
    "instagram_slides": ["Slide 1 hook (under 10 words)", "Slide 2 ...", "... 7-9 slides total, last slide = CTA"],
    "instagram_caption": "2-3 punchy lines + exactly 5 relevant hashtags",
    "x_hook": "a 1-2 line X/Twitter version of the hook",
    "inspired_by_title": "the exact real outlier title this is modeled on (title only)"
  }}

"winning_templates": array of up to 3:
  {{"template": "reusable hook/content pattern with ___ blanks",
    "why_it_works": "1 sentence psychological trigger",
    "proof": "highest-ratio real example from the data"}}
"""


def load_outliers(path="copy_outliers.json"):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    lines = []
    for o in data:
        flags = []
        if o.get("is_ai"):
            flags.append("AI")
        if o.get("is_short"):
            flags.append("SHORT")
        tag = f" [{','.join(flags)}]" if flags else ""
        lines.append(f"- [{o['ratio']}x | {o['views']:,} views] {o['title']}{tag}")
    return "\n".join(lines) if lines else "(no new outliers today)"


def call_gemini(prompt, retries=3):
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85, "responseMimeType": "application/json",
                             "maxOutputTokens": 8192},
    }
    for model in MODELS:  # try each model; fall back if one is overloaded
        url = f"{BASE}/models/{model}:generateContent?key={GEMINI_API_KEY}"
        for attempt in range(retries):
            r = requests.post(url, json=payload, timeout=150)
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
    with open("copy_outliers.json", encoding="utf-8") as f:
        raw = json.load(f)
    if not raw:
        print("😴 No new copy outliers today — keeping the last good pack.")
        return

    data = load_outliers()
    print("🧠 Sending copy outliers to Gemini...\n")
    pack = json.loads(call_gemini(PROMPT.format(data=data)))
    pack["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open("copy_pack.json", "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=4, ensure_ascii=False)

    # archive today's pack so past days stay openable on the dashboard
    os.makedirs("history", exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(f"history/copy_{day}.json", "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=4, ensure_ascii=False)
    try:
        with open("history/index.json", encoding="utf-8") as f:
            idx = json.load(f)
    except Exception:
        idx = {}
    idx.setdefault("copy", [])
    if day not in idx["copy"]:
        idx["copy"].append(day)
        idx["copy"].sort()
    with open("history/index.json", "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)

    print("=" * 60)
    print("✍️ TODAY'S COPY LAB IDEAS")
    for i in pack.get("ideas", []):
        slides = len(i.get("instagram_slides", []))
        print(f"  [{i.get('score','?'):>3}] ({i.get('category','?')}) {i.get('topic','')}")
        print(f"        hook: {i.get('hook','')[:70]}")
        print(f"        linkedin: {len(i.get('linkedin_post',''))} chars · carousel: {slides} slides")
    print(f"\n✅ {len(pack.get('ideas', []))} ideas saved to copy_pack.json")


if __name__ == "__main__":
    main()

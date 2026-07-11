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

# ---------------------------------------------------------------------------
# THE GRID LOGIC (1-2-3 Row Rhythm) — Mon-Wed and Thu-Sat are cohesive rows.
# Post 1 (Mon/Thu): Minimalist Quote Carousel (3-5 slides)
# Post 2 (Tue/Fri): High-Status Motion Reel (10s loop, frame-by-frame overlays)
# Post 3 (Wed/Sat): Structural Mechanism Breakdown Carousel (6-8 slides)
# Sunday: prepare Monday's Post 1 in advance.
# ---------------------------------------------------------------------------
POST_TYPES = {
    1: "Minimalist Quote Carousel (3-5 slides, high-level philosophical hook)",
    2: "High-Status Motion Reel (10-second minimal loop, minimal text overlays)",
    3: "Structural Mechanism Breakdown Carousel (6-8 slides, tactical, proof-heavy)",
}

SYSTEM = """ACT AS: Muhammad Anas's Creative Strategist & Automated Grid Manager.
GOAL: Build a high-authority Instagram grid for a high-ticket fitness coaching brand.

THE GRID LOGIC (The 1-2-3 Row Rhythm):
The grid is structured in horizontal 3-post rows. Every 3-day block (Mon-Wed and Thu-Sat) is a
single cohesive unit, in this sequence:
- POST 1 (Monday/Thursday): Minimalist Quote Carousel (3-5 slides). High-level philosophical hook.
- POST 2 (Tuesday/Friday): High-Status Motion Reel (10s minimal loop). Minimal text overlays.
- POST 3 (Wednesday/Saturday): Structural Mechanism Breakdown Carousel (6-8 slides). Tactical,
  proof-heavy content.

COHESION: Before generating, check the context of the previous 1-2 posts in the CURRENT row.
The visual theme (Gold/Black/White), the tone, and the message must flow into the next post
like an editorial magazine.

CONTENT & STYLE CONSTRAINTS (STRICT):
- VISUALS: consistent high-end Black, Gold, and White aesthetic.
- TEXT PACING: max 5-9 words per visual frame or slide. Scannable.
- TONE: high-status, clinical, contrarian.
- FORBIDDEN: never use AI-slop words ("delve", "unleash", "tapestry", "game-changer").
- THE DM FUNNEL: every SATURDAY post MUST conclude with a frictionless, number-based ManyChat
  DM trigger (e.g. "Comment 402").
- NO TUTORIALS: we are positioning, not teaching. No "How-to" headlines. Focus on identity and
  belief shifts.
- Never fabricate client results or fake numbers.

You are also handed today's REAL trending outliers from the niche (videos massively beating
their channel size). Use them as raw material for angles and belief-shift hooks — extract the
winning PATTERN, never copy the content.

Return ONLY valid JSON. No markdown, no commentary outside the JSON."""

PROMPT = """TODAY: {for_day}{prep_note} → generate POST {post_no}: {post_type}. Row: {row}.
{dm_line}

PREVIOUS POSTS IN THIS ROW (cohesion context):
{cohesion}

TODAY'S REAL NICHE OUTLIERS (trend fuel — extract patterns, don't copy):
{data}

Return JSON with EXACTLY these keys:

"instagram_grid": {{
  "for_day": "{for_day}",
  "post_number": {post_no},
  "post_type": "{post_type_short}",
  "row": "{row}",
  "strategic_rationale": "2-3 sentences: how this post links visually and thematically to the rest of the current row (the Cohesion Check)",
  {assets_field}
  "caption": "hyper-short scannable caption with clean emojis{dm_caption}",
  "dm_trigger": {dm_field},
  "theme_note": "one line describing the visual thread (colors/motif) to carry through this row"
}},

"ideas": array of 6 content ideas from the outlier data (used for the Topics & Hooks page and
future LinkedIn work), each:
  {{"topic": "...", "score": 0-100, "category": "mindset" | "mechanism" | "coaching-business" | "aesthetic",
    "why": "1 sentence why it's hot", "hook": "scroll-stopper line (no how-to phrasing)",
    "linkedin_post": "complete 120-180 word post with \\n line breaks, high-status tone, ends with a question",
    "x_hook": "1-2 line X version", "inspired_by_title": "exact outlier title (title only)"}},

"winning_templates": array of up to 3:
  {{"template": "reusable hook pattern with ___ blanks", "why_it_works": "1 sentence",
    "proof": "highest-ratio real example from the data"}}
"""


def grid_today():
    wd = datetime.now(timezone.utc).weekday()  # Mon=0 (9AM PKT run = same UTC date)
    if wd == 6:  # Sunday → prepare Monday's Post 1
        return 1, "Monday", "Mon–Wed", " (prepared today, Sunday, for tomorrow)", False
    post_no = [1, 2, 3, 1, 2, 3][wd]
    row = "Mon–Wed" if wd <= 2 else "Thu–Sat"
    day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][wd]
    return post_no, day, row, "", (wd == 5)


def cohesion_context():
    try:
        idx = json.load(open("history/index.json", encoding="utf-8")).get("copy", [])
    except Exception:
        idx = []
    ctx = []
    for day in sorted(idx)[-3:]:
        try:
            p = json.load(open(f"history/copy_{day}.json", encoding="utf-8"))
            g = p.get("instagram_grid")
            if g:
                first = (g.get("slides") or [f.get("overlay", "") for f in g.get("reel_frames", [])] or [""])[0]
                ctx.append(f"- {day}: POST {g.get('post_number')} ({g.get('post_type')}) · theme: "
                           f"{g.get('theme_note','')} · opened with: \"{first}\"")
        except Exception:
            pass
    return "\n".join(ctx[-2:]) or "(no previous grid posts yet — this post starts the grid; set the row's theme)"


def load_outliers(path="copy_outliers.json"):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return "\n".join(f"- [{o['ratio']}x | {o['views']:,} views] {o['title']}" for o in data) or "(no new outliers today)"


def call_gemini(prompt, retries=3):
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85, "responseMimeType": "application/json",
                             "maxOutputTokens": 24576},
    }
    for model in MODELS:
        url = f"{BASE}/models/{model}:generateContent?key={GEMINI_API_KEY}"
        for attempt in range(retries):
            try:
                r = requests.post(url, json=payload, timeout=150)
            except requests.exceptions.RequestException as e:
                wait = 10 * (attempt + 1)
                print(f"  ⏳ network hiccup ({type(e).__name__}), waiting {wait}s...")
                time.sleep(wait)
                continue
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
        print("😴 No new outliers today — keeping the last good pack.")
        return

    post_no, for_day, row, prep_note, dm_required = grid_today()
    if post_no == 2:
        assets_field = ('"reel_frames": [{"time": "0-2s", "overlay": "5-9 word overlay"}, '
                        '... 4-6 frames covering the full 10-second loop ...],')
    else:
        n = "3-5" if post_no == 1 else "6-8"
        assets_field = f'"slides": ["{n} slides, each max 5-9 words, slide 1 = the hook"],'
    dm_line = ("⚠️ IT IS SATURDAY: the post MUST end with a frictionless number-based ManyChat DM "
               "trigger (e.g. \"Comment 402\").") if dm_required else "No DM trigger required today (only Saturdays)."
    prompt = PROMPT.format(
        for_day=for_day, prep_note=prep_note, post_no=post_no,
        post_type=POST_TYPES[post_no], post_type_short=POST_TYPES[post_no].split(" (")[0],
        row=row, dm_line=dm_line, cohesion=cohesion_context(), data=load_outliers(),
        assets_field=assets_field,
        dm_caption=", ending with the DM trigger" if dm_required else "",
        dm_field='"Comment <3-digit number>"' if dm_required else '""',
    )

    print(f"🧠 Grid Manager: {for_day}{prep_note} → POST {post_no} ({POST_TYPES[post_no].split(' (')[0]})\n")
    pack = json.loads(call_gemini(prompt))
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

    g = pack.get("instagram_grid", {})
    print("=" * 60)
    print(f"🗓️  {g.get('for_day')} · POST {g.get('post_number')} · {g.get('post_type')} · row {g.get('row')}")
    assets = g.get("slides") or g.get("reel_frames") or []
    print(f"🖼️  assets: {len(assets)} {'slides' if g.get('slides') else 'reel frames'}")
    print(f"💬 caption: {(g.get('caption') or '')[:70]}")
    if g.get("dm_trigger"):
        print(f"📩 DM trigger: {g['dm_trigger']}")
    print(f"📋 ideas for topics/LinkedIn: {len(pack.get('ideas', []))}")
    print("\n✅ Saved to copy_pack.json")


if __name__ == "__main__":
    main()

import os
import sys
import json
import time
import random
from datetime import datetime, timezone, timedelta
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
OUTLIERS_FILE = "copy_outliers.json"
HOOK_BANK_FILE = "copy_hook_bank.json"
PACK_FILE = "copy_pack.json"

# ---------------------------------------------------------------------------
# THE GRID LOGIC (1-2-3 Row Rhythm) — posts run MONDAY–SATURDAY only.
# Post 1 (Mon/Thu): Minimalist Quote Carousel (3-5 slides)
# Post 2 (Tue/Fri): High-Status Motion Reel (10s loop, frame-by-frame overlays)
# Post 3 (Wed/Sat): Structural Mechanism Breakdown Carousel (6-8 slides)
# SUNDAY: rest day — nothing is generated.
# ---------------------------------------------------------------------------
POST_TYPES = {
    1: "Minimalist Quote Carousel (3-5 slides, high-level philosophical hook)",
    2: "High-Status Motion Reel (10-second minimal loop, minimal text overlays)",
    3: "Structural Mechanism Breakdown Carousel (6-8 slides, tactical, proof-heavy)",
}

SYSTEM = """ACT AS: Muhammad Anas's Creative Strategist & Automated Grid Manager.
GOAL: Build a high-authority Instagram grid for a high-ticket fitness coaching brand.

THE GRID LOGIC (The 1-2-3 Row Rhythm), running Monday-Saturday:
- POST 1 (Monday/Thursday): Minimalist Quote Carousel (3-5 slides). High-level philosophical hook.
- POST 2 (Tuesday/Friday): High-Status Motion Reel (10s minimal loop). Minimal text overlays.
- POST 3 (Wednesday/Saturday): Structural Mechanism Breakdown Carousel (6-8 slides). Tactical, proof-heavy.

COHESION: the visual theme (Gold/Black/White), tone, and message must flow into the next post in
the current 3-day row like an editorial magazine.

FRESHNESS (critical): every single day must be a DISTINCTLY DIFFERENT post — a new angle, a new
hook, a new belief-shift. NEVER reuse a hook, theme, or angle from the recent posts you are shown.
Repetition kills a personal brand.

CONTENT & STYLE CONSTRAINTS (STRICT):
- VISUALS: consistent high-end Black, Gold, and White aesthetic.
- TEXT PACING: max 5-9 words per visual frame or slide. Scannable.
- TONE: high-status, clinical, contrarian.
- FORBIDDEN: never use AI-slop words ("delve", "unleash", "tapestry", "game-changer").
- THE DM FUNNEL: every SATURDAY post MUST conclude with a frictionless, number-based ManyChat DM
  trigger (e.g. "Comment 402").
- NO TUTORIALS: we position, not teach. No "How-to" headlines. Focus on identity and belief shifts.
- Never fabricate client results or fake numbers.

You are handed a ROTATING pool of real trending topics from the niche as raw fuel. Each item is
TAGGED with the platform it came from ([YouTube] or [Instagram]). Extract the winning PATTERN into
an original belief-shift — never copy the topic. When the pool contains items from BOTH platforms
that touch the SAME theme, MERGE them: fuse the YouTube angle and the Instagram angle into one
sharper belief-shift (that cross-platform overlap is the strongest signal).

HASHTAGS: every generated post MUST include a set of relevant, mixed-reach Instagram hashtags
(a blend of niche + broader tags). Never invent fake/branded tags.

Return ONLY valid JSON. No markdown, no commentary outside the JSON."""

PROMPT = """TODAY: {for_day} → generate POST {post_no}: {post_type}. Row: {row}.
{dm_line}

RECENT POSTS — DO NOT repeat any of these hooks, themes, or angles (make today clearly different):
{recent}

COHESION CONTEXT (flow visually/thematically with the current row):
{cohesion}

TODAY'S ROTATING TREND POOL (fuel — extract patterns, never copy):
{data}

Return JSON with EXACTLY these keys:

"grid_options": array of EXACTLY 5 DISTINCT versions of this SAME post (all are POST {post_no} for {for_day}).
Anas will CHOOSE his favorite to publish, so the 5 must each use a clearly DIFFERENT hook, angle, and
belief-shift — never overlapping with each other or with the recent posts. Each object:
  {{
    "for_day": "{for_day}",
    "post_number": {post_no},
    "post_type": "{post_type_short}",
    "row": "{row}",
    "option_label": "2-4 word label naming THIS version's angle (e.g. 'Comfort trap', 'Identity shift')",
    "source_mix": "which platform(s) fueled this variant — 'YouTube', 'Instagram', or 'YouTube + Instagram' if you merged both",
    "strategic_rationale": "2-3 sentences: how this post links visually and thematically to the rest of the current row (the Cohesion Check)",
    {assets_field}
    "caption": "hyper-short scannable caption with clean emojis{dm_caption}",
    "hashtags": ["8-15 relevant Instagram hashtags (mix of niche + broad reach), no # symbol, no duplicates"],
    "dm_trigger": {dm_field},
    "theme_note": "one line describing the visual thread (colors/motif) to carry through this row"
  }},

"ideas": array of 6 FRESH content ideas from the pool (for the Topics & Hooks page + future LinkedIn),
each different from the recent posts:
  {{"topic": "...", "score": 0-100, "category": "mindset" | "mechanism" | "coaching-business" | "aesthetic",
    "why": "1 sentence why it's hot", "hook": "scroll-stopper line (no how-to phrasing)",
    "linkedin_post": "complete 120-180 word post with \\n line breaks, high-status tone, ends with a question",
    "x_hook": "1-2 line X version", "inspired_by_title": "exact pool title (title only)"}},

"winning_templates": array of up to 3:
  {{"template": "reusable hook pattern with ___ blanks", "why_it_works": "1 sentence", "proof": "a real pool example"}}
"""


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def grid_target():
    """Runs a day AHEAD: today's run prepares TOMORROW's post so Anas schedules it in advance.
    Tomorrow = Sunday (rest) means nothing to prepare → the pipeline is OFF today (that off-day
    is Saturday). Returns (post_no, target_day_name, row, target_date, dm_required)."""
    now = datetime.now(timezone.utc)
    tw = (now.weekday() + 1) % 7                       # tomorrow's weekday: Mon=0 .. Sun=6
    post_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    if tw == 6:                                         # tomorrow is Sunday → nothing to prepare
        return 0, "Sunday", "-", post_date, False
    post_no = [1, 2, 3, 1, 2, 3][tw]
    row = "Mon–Wed" if tw <= 2 else "Thu–Sat"
    day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][tw]
    return post_no, day, row, post_date, (tw == 5)     # dm required when tomorrow is Saturday


def _recent_grids(n):
    idx = _load("history/index.json", {}).get("copy", [])
    out = []
    for day in sorted(idx)[-n:]:
        p = _load(f"history/copy_{day}.json", {})
        g = p.get("instagram_grid")
        if g:
            first = (g.get("slides") or [f.get("overlay", "") for f in g.get("reel_frames", [])] or [""])[0]
            out.append((day, g, first))
    return out


def recent_hooks(n=8):
    rows = _recent_grids(n)
    lines = [f'- {day}: "{first}" ({g.get("post_type","")})' for day, g, first in rows if first]
    return "\n".join(lines) or "(none yet — this is one of the first posts)"


def cohesion_context():
    rows = _recent_grids(3)[-2:]
    lines = [f"- {day}: POST {g.get('post_number')} · theme: {g.get('theme_note','')} · opened: \"{first}\""
             for day, g, first in rows]
    return "\n".join(lines) or "(no previous grid posts — set this row's theme)"


SRC_LABEL = {"youtube": "YouTube", "instagram": "Instagram"}


def load_pool():
    """Rotating pool from the WHOLE accumulated hook bank + today's fresh outliers, each item
    TAGGED with its source platform, shuffled by day-of-year so the material differs every day.
    When Instagram data is present it lands here alongside YouTube so the brain can merge them."""
    yt = _load(OUTLIERS_FILE, []) + _load(HOOK_BANK_FILE, [])
    ig = _load("instagram_outliers.json", []) + _load("instagram_hook_bank.json", [])
    random.seed(datetime.now(timezone.utc).timetuple().tm_yday)

    def prep(items, src):
        seen, out = set(), []
        for it in items:
            t = (it.get("title") or "").strip()
            if not t or t.lower() in seen:
                continue
            seen.add(t.lower())
            out.append(f"[{src}] {t}")
        random.shuffle(out)
        return out

    yt_rows, ig_rows = prep(yt, "YouTube"), prep(ig, "Instagram")
    # balanced mix so BOTH platforms feed the merge (15 each when available)
    rows = yt_rows[:15] + ig_rows[:15]
    if len(rows) < 30:                       # backfill from whichever has more
        rows += yt_rows[15:15 + (30 - len(rows))] + ig_rows[15:15 + (30 - len(rows))]
    random.shuffle(rows)
    return "\n".join(f"- {r}" for r in rows[:30]) or "(no material yet)"


def call_gemini(prompt, retries=3):
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.95, "responseMimeType": "application/json",
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


def archive(pack, day=None):
    os.makedirs("history", exist_ok=True)
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(f"history/copy_{day}.json", "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=4, ensure_ascii=False)
    idx = _load("history/index.json", {})
    idx.setdefault("copy", [])
    if day not in idx["copy"]:
        idx["copy"].append(day)
        idx["copy"].sort()
    with open("history/index.json", "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)


def main():
    post_no, for_day, row, post_date, dm_required = grid_target()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # OFF day (Saturday): tomorrow is Sunday (rest). Nothing to prepare — leave the
    # already-showing Saturday post in place and exit without touching anything.
    if post_no == 0:
        print("🛑 Pipeline off today (Saturday). Tomorrow is Sunday — no post to prepare.")
        return

    # Build a FRESH, varied post every posting day (rotating pool + anti-repeat)
    if post_no == 2:
        assets_field = ('"reel_frames": [{"time": "0-2s", "overlay": "5-9 word overlay"}, '
                        '... 4-6 frames covering the full 10-second loop ...],')
    else:
        n = "3-5" if post_no == 1 else "6-8"
        assets_field = f'"slides": ["{n} slides, each max 5-9 words, slide 1 = the hook"],'
    dm_line = ("⚠️ IT IS SATURDAY: the post MUST end with a frictionless number-based ManyChat DM "
               "trigger (e.g. \"Comment 402\").") if dm_required else "No DM trigger today (Saturdays only)."

    prompt = PROMPT.format(
        for_day=for_day, post_no=post_no, post_type=POST_TYPES[post_no],
        post_type_short=POST_TYPES[post_no].split(" (")[0], row=row, dm_line=dm_line,
        recent=recent_hooks(), cohesion=cohesion_context(), data=load_pool(),
        assets_field=assets_field,
        dm_caption=", ending with the DM trigger" if dm_required else "",
        dm_field='"Comment <3-digit number>"' if dm_required else '""',
    )

    print(f"🧠 Grid Manager (a day ahead): preparing options for {for_day} ({post_date}) → POST {post_no}\n")
    pack = json.loads(call_gemini(prompt))
    pack["generated_at"] = now
    pack["rest_day"] = False
    pack["post_date"] = post_date        # the day this post should be published
    pack["for_day"] = for_day

    # 3 options to choose from (fall back gracefully if the model returned a single grid)
    opts = pack.get("grid_options")
    if not opts and pack.get("instagram_grid"):
        opts = [pack["instagram_grid"]]
    opts = opts or []
    for g in opts:
        g["post_date"] = post_date
        g["for_day"] = for_day
    pack["grid_options"] = opts
    pack["instagram_grid"] = opts[0] if opts else {}   # default selection = option 1 (HTML compat)

    with open(PACK_FILE, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=4, ensure_ascii=False)
    archive(pack, post_date)             # archive under the POSTING date, not the run date

    print("=" * 60)
    print(f"🗓️  PREPARED for {for_day} ({post_date}) · POST {post_no} · {len(opts)} options to choose from:")
    for i, g in enumerate(opts, 1):
        assets = g.get("slides") or g.get("reel_frames") or []
        hook = (assets[0] if isinstance(assets[0], str) else assets[0].get("overlay", "")) if assets else "—"
        print(f"   Option {i} [{g.get('option_label','')}] · {len(assets)} {'slides' if g.get('slides') else 'frames'} · hook: {hook}")
    if opts and opts[0].get("dm_trigger"):
        print(f"📩 DM: {opts[0]['dm_trigger']}")
    print("\n✅ Saved to copy_pack.json")


if __name__ == "__main__":
    from runstate import run_once
    run_once("copy_brain", main)

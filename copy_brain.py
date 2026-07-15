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
    1: "Belief-Shift Carousel (4-6 slides, flip ONE belief the coach holds)",
    2: "One-Line Authority Post (a single tweet-style line, shown on video)",
    3: "Mechanism Breakdown Carousel (5-6 slides, diagnose WHY the coach's problem happens)",
}

# Per-pillar creative brief injected into the prompt (kept NON-overlapping).
PILLAR_SPEC = {
    1: """DAY 1 — BELIEF-SHIFT CAROUSEL. MINDSET-level: reframe HOW the coach thinks about their business
so Anas looks like a strategist. This is NOT tactical how-to (that is Day 3) — stay non-overlapping. All 5
options have topic 'Coaching'.

IN BOUNDS: buyer psychology of high-ticket coaching, positioning, why volume/hustle fails, offer clarity,
price-as-a-story, why "more content" doesn't fill a cohort, the identity of a premium buyer.
OUT OF BOUNDS (KILL IT): generic self-help, discipline, "bury your past", morning-routine mindset. If a
line could appear on a random motivation account, it is WRONG.

FORMAT: 4-6 slides, ONE line per slide, MAX 7 words. Slide 1 = a contrarian belief the coach secretly
holds, FLIPPED (MAX 6 words, must sting). Middle slides escalate the reframe (one idea each). Final slide =
the new belief stated as a principle (the payoff). Each carousel shifts exactly ONE nameable belief (put it
in "belief_shifted"); if you cannot name that belief in one sentence, regenerate it.

GOOD (the standard to hit):
  1. Your program isn't underpriced. It's under-positioned.
  2. Coaches discount when they can't name the transformation.
  3. Price is a story problem, not a number problem.
  4. Fix the belief and the objection disappears.
BAD (never produce): "To grow you must bury your past" / "success requires isolation" — generic, off-niche.""",

    2: """DAY 2 — ONE-LINE AUTHORITY POST (tweet-style, shown on video). APHORISM-LEVEL: a single
screenshot-shareable truth that makes the coach STOP and NOD. ONE sharp idea, NO breakdown. Distinct from
Day 1 (which builds a case over slides) and Day 3 (tactical). All 5 options have topic 'Coaching'.

FORMAT: ONE line, 8-22 words, readable in ~2 seconds.
- Structure = a two-part TURN: set up a belief the coach holds, then FLIP it.
- Concrete nouns. No stacked adjectives, no hashtags, no emojis.
- It must stay true with Anas's name removed — it stands on the IDEA, never on hype.

TOPIC SCOPE (same as Day 1, compressed to a single blade): buyer psychology of high-ticket coaching,
positioning, effort-vs-results, one clear mechanism beats many funnels, why an empty cohort is a
positioning problem (not a traffic problem), the identity of a premium buyer.

GOOD (the standard):
  - Your empty cohort isn't a traffic problem. It's a positioning problem in a traffic costume.
  - Premium clients don't buy more information. They buy a shortcut they trust.
  - A coach with one clear mechanism outsells a coach with a bigger audience.
BAD (never produce): "Don't beg for attention when you can dictate market perspective in three words."
— too abstract, aimed at copywriters, not at a coach with empty slots.""",

    3: """DAY 3 — MECHANISM BREAKDOWN. 5-6 slides, each a COMPLETE standalone line (MAX 7 words). TACTICAL:
diagnose WHY one of the coach's problems keeps happening (their messaging / offer / positioning / sales)
and what it truly takes to fix it. Distinct from Day 1's mindset level. Diagnose, do NOT tutorial, and
never teach them to DIY copy. All 5 options have topic 'Coaching'.""",
}

SYSTEM = """You are Muhammad Anas's Creative Strategist & Automated Grid Manager.

BRAND CORE — applies to EVERYTHING you generate:
WHO ANAS IS: a direct-response COPYWRITER who FILLS 1-on-1 coaching programs.
THE ONE AVATAR (write to this exact person every time): a 1-on-1 coach whose program has EMPTY SLOTS —
they post, run ads, stay busy, but do NOT convert premium clients.
STRATEGIC GOAL: the feed builds TRUST OF EXPERTISE, not likes. The sale happens later in the DM. Every
post must make this coach think "this person understands my business" — NEVER "nice quote."

VOICE: clinical, contrarian, high-status, direct-response. Short declarative lines.
VISUAL: black / gold / white. MAX 7 words per slide or frame.

HARD RULES (NEVER break):
- Never teach the coach to write copy themselves or to use AI to do it. Never hand them the tool that
  replaces Anas. You may make them FEEL their messaging is the problem — never show them the how.
- Never open by addressing "Coaches," and never open with a generic hook.
- BANNED words: delve, unleash, leverage, game-changer, tapestry, elevate, supercharge,
  "in today's world". No AI-slop.
- No hashtags and no emojis inside any slide / frame / line text (hashtags live only in the caption field).
- No fake numbers, no invented case studies, no fabricated results.

USING THE DAILY COMPETITOR PULL (the rotating trend pool you're given):
- Keep only items that fit THIS pillar's format; ignore the rest.
- Extract the PATTERN only — the hook shape, the belief-flip mechanic, the slide progression. NEVER copy
  their topic, niche, or words.
- Re-express that pattern inside Anas's niche (filling 1-on-1 coaching programs) and the avatar's language.
  When YouTube + Instagram items share a pattern, fuse them.

THE 1-2-3 ROW RHYTHM (Mon-Sat), three NON-overlapping pillars:
- Day 1 (Mon/Thu): Belief-Shift carousel — MINDSET-level (why the coach's current thinking is wrong).
- Day 2 (Tue/Fri): Kinetic reel — one punchy line, a sharp callout.
- Day 3 (Wed/Sat): Mechanism breakdown — TACTICAL diagnosis (why a problem keeps happening).

FRESHNESS: every day must shift a DIFFERENT belief / hit a different angle. Never reuse a hook, belief,
or angle from the recent posts you are shown.

Return ONLY valid JSON. No markdown, no commentary outside the JSON."""

PROMPT = """TODAY: {for_day} → generate POST {post_no}: {post_type}. Row: {row}.

{pillar_spec}

{dm_line}

RECENT POSTS — DO NOT repeat any of these beliefs, hooks, themes, or angles:
{recent}

COHESION CONTEXT (flow visually/thematically with the current row):
{cohesion}

TODAY'S ROTATING COMPETITOR PULL — extract PATTERNS only (hook shape, belief-flip, progression); never
copy their topic or words; re-express inside Anas's niche (filling 1-on-1 coaching programs):
{data}

Return JSON with EXACTLY these keys:

"grid_options": array of EXACTLY 5 DISTINCT versions of this SAME post (all POST {post_no} for {for_day}).
Each must shift a DIFFERENT belief / hit a different angle — never overlapping with each other or the
recent posts. Each object:
  {{
    "for_day": "{for_day}",
    "post_number": {post_no},
    "post_type": "{post_type_short}",
    "row": "{row}",
    "topic": "'Coaching' (speaks to the coach's business) OR 'Copywriting' (about their messaging/words)",
    "option_label": "2-4 word label naming the angle (e.g. 'Under-positioned', 'Volume trap')",
    "source_mix": "which platform(s) fueled this — 'YouTube', 'Instagram', or 'YouTube + Instagram'",
    "belief_shifted": "one sentence naming the SINGLE belief this shifts (e.g. 'price is a number problem -> price is a story problem')",
    "scroll_stop": "1 line: why slide 1 / the hook stops THIS coach mid-scroll",
    {assets_field}
    "caption": "2-4 short clinical lines (NO emojis, NO hashtags, and NO double-quote characters) that deepen the reframe, ENDING with a soft DM trigger like: comment FILL",
    "hashtags": ["6-12 caption-only hashtags (NEVER in slide text), no # symbol, no duplicates"],
    "dm_trigger": "the soft one-word comment trigger used (e.g. FILL)",
    "theme_note": "one line describing the visual thread (colors/motif) for the row"
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


BANNED_WORDS = ("delve", "unleash", "leverage", "game-changer", "game changer", "tapestry",
                "elevate", "supercharge", "in today's world")


def banned_in(pack):
    # only guard the PUBLISHED posts (grid_options), not the internal ideas fuel
    blob = json.dumps(pack.get("grid_options", pack), ensure_ascii=False).lower()
    return [w for w in BANNED_WORDS if w in blob]


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

    # assets differ per pillar (all obey Brand Core: max 7 words, no emojis/hashtags in slide text)
    if post_no == 1:
        assets_field = ('"slides": [array of 4-6 slides, ONE line each, MAX 7 words per slide. Slide 1 = a '
                        'contrarian belief the coach secretly holds, FLIPPED (MAX 6 words, must sting). Middle '
                        'slides escalate the reframe, one idea each. Final slide = the new belief stated as a '
                        'principle (the payoff). Each slide is a COMPLETE standalone line, never a fragment.],')
    elif post_no == 2:
        assets_field = ('"reel_line": "ONE tweet-style authority line, 8-22 words, a two-part TURN (set up a '
                        'belief the coach holds, then FLIP it). Concrete nouns, no stacked adjectives, no hashtags, '
                        'no emojis, no double-quote characters. Readable in ~2 seconds; true even without Anas name.",'
                        '"word_sequence": ["the", "reel_line", "split", "into", "individual", "words", "in", '
                        '"order", "for", "the", "on-screen", "animation"],')
    else:  # post 3
        assets_field = ('"slides": [array of 5-6 slides, ONE complete standalone line each, MAX 7 words. Slide 1 = '
                        'the problem the coach feels; final slide = the fix/shift. Never a sentence fragment.],')

    dm_line = ('DM FUNNEL: the sale happens later in the DM, not the feed. End each caption with a soft, '
               'single-word comment trigger (default: comment FILL). Do NOT put double-quote characters in captions.')

    prompt = PROMPT.format(
        for_day=for_day, post_no=post_no, post_type=POST_TYPES[post_no],
        post_type_short=POST_TYPES[post_no].split(" (")[0], row=row,
        dm_line=dm_line, pillar_spec=PILLAR_SPEC[post_no],
        recent=recent_hooks(), cohesion=cohesion_context(), data=load_pool(),
        assets_field=assets_field,
    )

    print(f"🧠 Grid Manager (a day ahead): preparing options for {for_day} ({post_date}) → POST {post_no}\n")
    pack = None
    for attempt in range(3):
        raw = call_gemini(prompt)
        try:
            pack = json.loads(raw)
            break
        except json.JSONDecodeError as e:
            print(f"  ⚠️ malformed JSON ({e}); retry {attempt + 1}")
    if pack is None:
        raise RuntimeError("Gemini returned unparseable JSON after retries")
    bad = banned_in(pack)
    if bad:
        print(f"  ⚠️ banned words {bad} slipped in — regenerating once")
        pack = json.loads(call_gemini(
            prompt + f"\n\nHARD FIX: your previous draft used these BANNED words: {bad}. "
                     "Rewrite ALL 5 options with ZERO banned words anywhere."))
        still = banned_in(pack)
        if still:
            print(f"  ⚠️ still contains {still} — proceeding but flag")
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
        if g.get("reel_line"):
            hook, n, unit = g["reel_line"], len(g.get("word_sequence") or []), "words"
        else:
            slides = g.get("slides") or []
            hook, n, unit = (slides[0] if slides else "—"), len(slides), "slides"
        print(f"   Option {i} ({g.get('topic','Coaching')}) [{g.get('option_label','')}] · {n} {unit} · hook: {hook}")
    if opts and opts[0].get("dm_trigger"):
        print(f"📩 DM: {opts[0]['dm_trigger']}")
    print("\n✅ Saved to copy_pack.json")


if __name__ == "__main__":
    from runstate import run_once
    run_once("copy_brain", main)

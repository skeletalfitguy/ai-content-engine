import os
import re
import sys
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
if not APIFY_TOKEN:
    raise ValueError("❌ Missing APIFY_API_TOKEN inside your .env file!")

# ---------------------------------------------------------------------------
# ANAS INSTAGRAM ENGINE — scrapes real winning posts from the coaching niche via
# Apify, so the Grid Manager is fueled by ACTUAL Instagram signal (not just
# YouTube). Budgeted to ~$4.8/month: 4 rotating hashtags × 15 posts = 60/day,
# measured at ~$0.0026/result ≈ $0.16/day ≈ $4.7/mo (stays under the $5 free tier).
# ---------------------------------------------------------------------------
ACTOR = "apify~instagram-hashtag-scraper"
RESULTS_PER_TAG = 15
TAGS_PER_DAY = 4
KEEP_TOP = 25                     # after filtering, keep the strongest for the pool
MIN_LETTERS = 15                  # a usable hook needs this many real letters (kills emoji/#-only)

# Rotating pool — every day picks a fresh window so all tags get covered over time.
HASHTAGS = [
    "onlinefitnesscoach", "highticketfitness", "fitnessmindset", "transformationcoach",
    "fitnesscoaching", "onlinecoaching", "disciplineovermotivation", "mindsetcoach",
    "physiquetransformation", "naturalbodybuilding", "fatlossjourney", "musclebuilding",
    "highperformance", "selfdiscipline", "gymmotivation", "aestheticphysique",
    "fitnessbusiness", "coachingbusiness", "hypertrophytraining", "bodyrecomposition",
]

SEEN_FILE = "instagram_seen.json"
HOOK_BANK_FILE = "instagram_hook_bank.json"
OUTLIERS_FILE = "instagram_outliers.json"

# Obvious promo/tool accounts we don't want polluting the hook pool.
SPAM_HINTS = ("ai_", "_ai", "aiapp", "tool", "app_", "_app", "shop", "store", "deals",
              "promo", "bot", "generator", "template")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def todays_hashtags():
    doy = datetime.now(timezone.utc).timetuple().tm_yday
    start = (doy * TAGS_PER_DAY) % len(HASHTAGS)
    return [HASHTAGS[(start + i) % len(HASHTAGS)] for i in range(TAGS_PER_DAY)]


def run_scraper(tags):
    """Async run + poll (robust for larger pulls). Returns (items, usd)."""
    H = {"Authorization": "Bearer " + APIFY_TOKEN}
    payload = {"hashtags": tags, "resultsType": "posts", "resultsLimit": RESULTS_PER_TAG}
    r = requests.post(f"https://api.apify.com/v2/acts/{ACTOR}/runs", headers=H, json=payload, timeout=60)
    r.raise_for_status()
    run = r.json()["data"]
    rid = run["id"]
    print(f"🚀 scrape run {rid} · tags {tags}")
    status, data = "RUNNING", run
    for _ in range(120):
        time.sleep(4)
        data = requests.get(f"https://api.apify.com/v2/actor-runs/{rid}", headers=H, timeout=30).json()["data"]
        status = data["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    usd = data.get("usageTotalUsd")
    if status != "SUCCEEDED":
        print(f"  ⚠️ run ended {status} (usage ${usd})")
        return [], usd or 0
    dsid = data["defaultDatasetId"]
    items = requests.get(
        f"https://api.apify.com/v2/datasets/{dsid}/items?clean=true&format=json",
        headers=H, timeout=90).json()
    print(f"  ✓ {len(items)} raw posts · cost ${usd}")
    return (items if isinstance(items, list) else []), usd or 0


def caption_hook(caption):
    """First real sentence/line of the caption with hashtags stripped out — skips
    emoji-only and hashtag-only lines so the hook is actual words."""
    for line in (caption or "").splitlines():
        t = re.sub(r"#\w+", "", line).strip()
        if sum(c.isalpha() for c in t) >= MIN_LETTERS:
            return re.sub(r"\s+", " ", t)[:160]
    t = re.sub(r"#\w+", " ", caption or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t[:160] if sum(c.isalpha() for c in t) >= MIN_LETTERS else ""


def is_spam(username, likes, comments):
    u = (username or "").lower()
    if any(h in u for h in SPAM_HINTS) and (likes or 0) < 200:
        return True
    return (likes or 0) <= 0 and (comments or 0) <= 0     # no real engagement / dead post


def find_winners(items, seen):
    winners = []
    for it in items:
        pid = it.get("id") or it.get("shortCode") or it.get("url")
        if not pid or pid in seen:
            continue
        caption = it.get("caption") or ""
        hook = caption_hook(caption)
        if not hook:                      # no usable words (emoji/hashtag-only) → skip
            continue
        likes = it.get("likesCount") or 0
        comments = it.get("commentsCount") or 0
        views = it.get("videoViewCount") or it.get("videoPlayCount") or 0
        user = it.get("ownerUsername") or ""
        if is_spam(user, likes, comments):
            continue
        engagement = max(likes, 0) + max(comments, 0) * 6 + max(views, 0) // 20
        ptype = (it.get("type") or "").lower()
        kind = "reel" if ("video" in ptype or it.get("productType") == "clips") else \
               "carousel" if ptype == "sidecar" else "image"
        winners.append({
            "post_id": pid,
            "title": hook,
            "hook": hook,
            "caption": caption[:600],
            "username": user,
            "url": it.get("url", ""),
            "likes": likes,
            "comments": comments,
            "views": views,
            "engagement": engagement,
            "kind": kind,
            "source": "instagram",
            "hashtags": (it.get("hashtags") or [])[:15],
        })
    winners.sort(key=lambda w: w["engagement"], reverse=True)
    return winners[:KEEP_TOP]


def main():
    print("📸 Anas Instagram engine — hashtag winner scan\n")
    seen = set(load_json(SEEN_FILE, []))
    tags = todays_hashtags()
    items, usd = run_scraper(tags)
    winners = find_winners(items, seen)

    with open(OUTLIERS_FILE, "w", encoding="utf-8") as f:
        json.dump(winners, f, indent=4, ensure_ascii=False)

    seen.update(w["post_id"] for w in winners)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)

    bank = load_json(HOOK_BANK_FILE, [])
    known = {b.get("title") for b in bank}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for w in winners:
        if w["title"] not in known:
            bank.append({"title": w["title"], "hook": w["hook"], "ratio": None,
                         "views": w["likes"], "url": w["url"], "username": w["username"],
                         "source": "instagram", "hashtags": w["hashtags"], "added": today})
    with open(HOOK_BANK_FILE, "w", encoding="utf-8") as f:
        json.dump(bank, f, indent=4, ensure_ascii=False)

    print(f"\n✅ {len(winners)} IG winners · bank now {len(bank)} · today's cost ${usd}")


if __name__ == "__main__":
    main()

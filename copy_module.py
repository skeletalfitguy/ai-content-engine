import os
import re
import sys
import json
import isodate
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("❌ Missing YOUTUBE_API_KEY inside your .env file!")
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# ---------------------------------------------------------------------------
# ANAS COPY LAB — research engine for the HIGH-TICKET FITNESS COACHING brand grid.
# ~65% of daily YouTube quota (65 searches x 100 = 6,500 + ~80 overhead ≈ 6,580).
# Feeds: quote-carousel material (mindset/identity), mechanism breakdowns
# (training/nutrition/coaching science), reel concepts (high-status aesthetic),
# and coaching-business positioning angles.
# ---------------------------------------------------------------------------
NICHE_QUERIES = [
    # high-ticket coaching business (13)
    "high ticket fitness coaching",
    "online fitness coaching business",
    "how to get fitness coaching clients",
    "fitness coach content strategy",
    "personal trainer business",
    "online coaching offer",
    "high ticket coaching clients",
    "fitness coaching sales",
    "why most fitness coaches fail",
    "fitness coach marketing",
    "scale online coaching business",
    "premium coaching brand",
    "coaching business mistakes",
    # mindset / identity / discipline (13)
    "discipline over motivation",
    "mindset of high achievers",
    "identity change habits",
    "self discipline rules",
    "delayed gratification success",
    "stoic discipline",
    "mental toughness training",
    "why discipline beats talent",
    "habits of successful men",
    "dopamine detox discipline",
    "hard truths about success",
    "standards over goals",
    "high standards lifestyle",
    # contrarian fitness / training truths (13)
    "fitness industry lies",
    "why your workout doesn't work",
    "training mistakes lifters make",
    "hypertrophy science explained",
    "why cardio is overrated",
    "strength training truths",
    "muscle building myths",
    "fat loss myths",
    "why you're not building muscle",
    "minimalist training",
    "training frequency science",
    "progressive overload explained",
    "natural lifter limits",
    # transformation / physique psychology (13)
    "body transformation psychology",
    "physique transformation lessons",
    "what getting lean teaches you",
    "aesthetic physique",
    "body recomposition explained",
    "why transformations fail",
    "12 week transformation truth",
    "lessons from losing fat",
    "building muscle changed my life",
    "gym changed my life",
    "fitness attractiveness science",
    "testosterone lifestyle optimization",
    "sleep recovery muscle growth",
    # high-status aesthetic / reel material (6)
    "old money aesthetic",
    "luxury lifestyle motivation",
    "high status body language",
    "quiet luxury brand",
    "cinematic gym motivation",
    "gym aesthetic edit",
    # instagram growth / dm funnel for coaches (7)
    "manychat instagram automation",
    "instagram dm funnel",
    "instagram carousel strategy",
    "instagram grid aesthetic",
    "content strategy for coaches",
    "storytelling for coaches",
    "alex hormozi coaching business",
]

# Title must clearly be in the fitness-coaching / discipline / high-status world
CORE = ("coach", "fitness", "gym", "train", "muscle", "physique", "transformation",
        "fat loss", "lean", "hypertrophy", "lifter", "lifting", "workout", "cardio",
        "strength", "discipline", "mindset", "habit", "dopamine", "stoic", "success",
        "high ticket", "high-ticket", "testosterone", "recovery", "aesthetic",
        "old money", "luxury", "status", "instagram", "carousel", "manychat",
        "dm funnel", "content", "offer", "client", "motivation", "standards", "body")
AI_T = ("chatgpt", "claude", "gemini", "artificial intelligence", "ai tool")
BIZ = ("coach", "fitness", "content", "business", "brand", "client", "market", "sell")

DAYS_BACK = 120
MAX_PER_QUERY = 40
OUTLIER_THRESHOLD = 2.5        # views >= 2.5x subs (copy niche runs on smaller channels)
BIG_HIT_VIEWS = 200_000        # ...OR big absolute views for this niche
MIN_VIEWS = 20_000             # floor to kill flukes

SEEN_FILE = "copy_seen.json"
HOOK_BANK_FILE = "copy_hook_bank.json"
OUTLIERS_FILE = "copy_outliers.json"


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def is_copy_niche(title):
    t = " " + title.lower() + " "
    if any(k in t for k in CORE):
        return True
    has_ai = any(a in t for a in AI_T) or re.search(r"\bai\b", t)
    return bool(has_ai and any(b in t for b in BIZ))


def search_video_ids():
    after = (datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)).isoformat()
    ids = set()
    for q in NICHE_QUERIES:
        print(f"🔎 {q}")
        try:
            res = youtube.search().list(
                part="id", q=q, type="video",
                order="viewCount", publishedAfter=after, maxResults=MAX_PER_QUERY,
            ).execute()
            for it in res.get("items", []):
                ids.add(it["id"]["videoId"])
        except Exception as e:
            print(f"  ❌ search error: {e}")
    print(f"\n📦 {len(ids)} unique candidates\n")
    return list(ids)


def subs_for(channel_ids):
    out = {}
    ids = list(channel_ids)
    for i in range(0, len(ids), 50):
        try:
            res = youtube.channels().list(part="statistics", id=",".join(ids[i:i + 50])).execute()
            for c in res.get("items", []):
                out[c["id"]] = int(c["statistics"].get("subscriberCount", 0))
        except Exception as e:
            print(f"  ❌ channel error: {e}")
    return out


def extract_hook(transcript):
    if not transcript or transcript.startswith("["):
        return ""
    for sep in [". ", "? ", "! "]:
        if sep in transcript[:200]:
            return transcript.split(sep)[0].strip() + sep.strip()
    return transcript[:140].strip()


def find_outliers(video_ids, seen):
    outliers = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            res = youtube.videos().list(
                part="snippet,statistics,contentDetails", id=",".join(batch)
            ).execute()
        except Exception as e:
            print(f"  ❌ video error: {e}")
            continue
        items = res.get("items", [])
        subs_map = subs_for({it["snippet"]["channelId"] for it in items})
        for item in items:
            vid = item["id"]
            if vid in seen:
                continue
            views = int(item["statistics"].get("viewCount", 0))
            dur_raw = item.get("contentDetails", {}).get("duration")
            if not dur_raw:
                continue  # live streams / premieres have no duration
            duration = isodate.parse_duration(dur_raw).total_seconds()
            title = item["snippet"]["title"]
            subs = subs_map.get(item["snippet"]["channelId"], 0)

            if views < MIN_VIEWS or not is_copy_niche(title):
                continue
            ratio = views / subs if subs else 0
            if ratio < OUTLIER_THRESHOLD and views < BIG_HIT_VIEWS:
                continue

            try:
                fetched = YouTubeTranscriptApi().fetch(vid, languages=["en"])
                transcript = " ".join(s.text for s in fetched)[:700]
            except Exception:
                transcript = "[No English Transcript]"

            tl = title.lower()
            is_ai = bool(re.search(r"\bai\b", tl)) or any(a in tl for a in AI_T)
            desc = item["snippet"].get("description", "")
            hashtags = list(dict.fromkeys(re.findall(r"#(\w+)", title + " " + desc)))[:12]
            outliers.append({
                "video_id": vid,
                "title": title,
                "channel": item["snippet"]["channelTitle"],
                "url": f"https://youtube.com/watch?v={vid}" if duration > 62
                       else f"https://youtube.com/shorts/{vid}",
                "views": views,
                "subscribers": subs,
                "ratio": round(ratio, 2),
                "is_short": duration <= 62,
                "is_ai": is_ai,
                "source": "youtube",
                "hashtags": hashtags,
                "hook": extract_hook(transcript) or title,
                "transcript": transcript,
            })
            print(f"🔥 {ratio:>6.0f}x  {views:>11,}  {title[:60]}")
    return outliers


def main():
    print("✍️ Anas Copy Lab — niche outlier scan\n")
    seen = set(load_json(SEEN_FILE, []))
    ids = search_video_ids()
    outliers = find_outliers(ids, seen)
    outliers.sort(key=lambda o: o["ratio"], reverse=True)
    outliers = outliers[:40]  # keep the pack tight

    with open(OUTLIERS_FILE, "w", encoding="utf-8") as f:
        json.dump(outliers, f, indent=4, ensure_ascii=False)

    seen.update(o["video_id"] for o in outliers)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)

    bank = load_json(HOOK_BANK_FILE, [])
    known = {b["title"] for b in bank}
    for o in outliers:
        if o["title"] not in known:
            bank.append({"title": o["title"], "hook": o["hook"], "ratio": o["ratio"],
                         "views": o["views"], "url": o["url"],
                         "source": o.get("source", "youtube"), "hashtags": o.get("hashtags", []),
                         "added": datetime.now(timezone.utc).strftime("%Y-%m-%d")})
    with open(HOOK_BANK_FILE, "w", encoding="utf-8") as f:
        json.dump(bank, f, indent=4, ensure_ascii=False)

    print(f"\n✅ {len(outliers)} new outliers · copy hook bank now {len(bank)} entries")


if __name__ == "__main__":
    from runstate import run_once
    run_once("copy_module", main)

import os
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
# NICHE: FITNESS "what happens to your body / inside your body" shorts.
# We discover what is winning across all of YouTube, not a fixed channel list.
# ---------------------------------------------------------------------------
# ~18% of the daily YouTube quota (17 searches x 100 units = 1,700 + ~30 overhead
# = ~1,730 units of 10,000). Leaves ~82% free for the other dashboards you'll add.
NICHE_QUERIES = [
    "what happens to your body when you workout",
    "what happens inside your body when you exercise",
    "what happens to your muscles when you lift weights",
    "what happens to your body when you do pushups everyday",
    "what happens to your body when you stop working out",
    "running vs walking what happens inside your body",
    "what happens if you do plank everyday",
    "what happens to your body when you run everyday",
    "what happens to your body when you do squats everyday",
    "what happens inside your body when you do cardio",
    "pushups vs pullups what happens inside your body",
    "what happens to your body when you stretch everyday",
    "what happens to your body when you do situps everyday",
    "cardio vs weights what happens inside your body",
    "what happens inside your body when you do pull ups",
    "what happens to your body when you cycle everyday",
    "what happens to your body when you skip the gym",
    "what happens to your body when you do burpees everyday",
    "what happens to your body when you jump rope everyday",
    "what happens inside your body when you sprint",
]

# Only keep videos whose title is clearly FITNESS (kills diet/pregnancy/random noise)
FITNESS_WORDS = (
    "workout", "muscle", "gym", "exercise", "pushup", "push-up", "push up",
    "lift", "weight", "run", "walking", "squat", "stretch", "cardio", "train",
    "abs", "plank", "cycle", "cycling", "boxing", "punch", "stairs", "protein",
    "posture", "fat loss", "calorie", "sit-up", "situp", "burpee", "jog",
)

DAYS_BACK = 150                  # wider pool; dedup keeps each day's brief fresh
MAX_PER_QUERY = 40
OUTLIER_THRESHOLD = 8.0          # views >= 8x subs  (small-channel breakout)
BIG_HIT_VIEWS = 2_000_000        # ...OR huge absolute views regardless of ratio
MIN_VIEWS = 150_000              # floor to kill flukes

SEEN_FILE = "seen_videos.json"
HOOK_BANK_FILE = "hook_bank.json"
OUTLIERS_FILE = "youtube_outliers.json"


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def is_fitness(title):
    t = title.lower()
    return "what happens" in t and any(w in t for w in FITNESS_WORDS)


def search_video_ids():
    after = (datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)).isoformat()
    ids = set()
    for q in NICHE_QUERIES:
        print(f"🔎 {q}")
        try:
            res = youtube.search().list(
                part="id", q=q, type="video", videoDuration="short",
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
        if sep in transcript[:160]:
            return transcript.split(sep)[0].strip() + sep.strip()
    return transcript[:120].strip()


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
                continue  # already shown on a previous day
            views = int(item["statistics"].get("viewCount", 0))
            duration = isodate.parse_duration(item["contentDetails"]["duration"]).total_seconds()
            title = item["snippet"]["title"]
            subs = subs_map.get(item["snippet"]["channelId"], 0)

            if duration > 60 or views < MIN_VIEWS or not is_fitness(title):
                continue
            ratio = views / subs if subs else 0
            if ratio < OUTLIER_THRESHOLD and views < BIG_HIT_VIEWS:
                continue

            try:
                fetched = YouTubeTranscriptApi().fetch(vid, languages=["en"])
                transcript = " ".join(s.text for s in fetched)
            except Exception:
                transcript = "[No English Transcript]"

            tl = title.lower()
            outliers.append({
                "video_id": vid,
                "title": title,
                "channel": item["snippet"]["channelTitle"],
                "url": f"https://youtube.com/shorts/{vid}",
                "views": views,
                "subscribers": subs,
                "ratio": round(ratio, 2),
                "is_vs": " vs " in tl or " vs. " in tl,
                "is_everyday": "every day" in tl or "everyday" in tl or "daily" in tl,
                "hook": extract_hook(transcript) or title,
                "transcript": transcript,
            })
            print(f"🔥 {ratio:>6.0f}x  {views:>11,}  {title[:60]}")
    return outliers


def main():
    print("🎬 Fitness niche outlier scan\n")
    seen = set(load_json(SEEN_FILE, []))
    ids = search_video_ids()
    outliers = find_outliers(ids, seen)
    outliers.sort(key=lambda o: (o["is_vs"], o["ratio"]), reverse=True)

    # today's fresh outliers
    with open(OUTLIERS_FILE, "w", encoding="utf-8") as f:
        json.dump(outliers, f, indent=4, ensure_ascii=False)

    # remember what we showed (dedup) + grow the hook bank
    seen.update(o["video_id"] for o in outliers)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)

    bank = load_json(HOOK_BANK_FILE, [])
    known = {b["title"] for b in bank}
    for o in outliers:
        if o["title"] not in known:
            bank.append({"title": o["title"], "hook": o["hook"], "ratio": o["ratio"],
                         "views": o["views"], "url": o["url"],
                         "added": datetime.now(timezone.utc).strftime("%Y-%m-%d")})
    with open(HOOK_BANK_FILE, "w", encoding="utf-8") as f:
        json.dump(bank, f, indent=4, ensure_ascii=False)

    print(f"\n✅ {len(outliers)} new outliers · hook bank now {len(bank)} entries")


if __name__ == "__main__":
    main()

import os
import re
import sys
import json
import html
from datetime import datetime, timezone
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------
# ANAS JOBS RADAR — pulls remote copywriting / email / ads / marketing jobs
# from FREE job-board APIs (no key, no YouTube quota). Any relevant job is a win.
# ---------------------------------------------------------------------------
# Match these against the TITLE only (strongest signal; tags were too noisy).
KEYWORDS = (
    "copywriter", "copywriting", "copy writer", "ad copy", "advertising copy",
    "email marketing", "email copy", "email specialist", "lifecycle market",
    "retention market", "crm market",
    "content writer", "content marketing", "content marketer", "content strategist",
    "content creator", "content specialist",
    "creative strategist", "creative strategy", "creative copywriter",
    "marketing copywriter", "marketing writer", "conversion copy", "sales copywriter",
    "sales copy", "direct response", "direct-response", "brand copywriter",
    "brand writer", "newsletter writer", "seo writer", "seo copywriter", "seo content",
    "ugc", "social media manager", "social media specialist", "social media coordinator",
    "social media strategist", "growth marketer", "performance marketer",
    "digital marketer", "digital marketing", "marketing specialist",
    "marketing coordinator", "marketing associate", "marketing manager",
)
# exclude even if a keyword matched (kills adjacent-but-wrong roles)
NEGATIVE = (
    "technical writer", "grant writer", "medical writer", "proposal", "scrum",
    "engineer", "developer", "devops", "clerk", "administrative assistant",
    "executive assistant", "virtual assistant", "data ", "supply chain", "recruiter",
    "sales development", "account executive", "media buyer", "accountant", "bookkeeper",
    "project manager", "product manager", "designer", "analyst", "paralegal",
    "human resources", "hr business",
)

SEEN_FILE = "jobs_seen.json"
RAW_FILE = "jobs_raw.json"
UA = {"User-Agent": "Mozilla/5.0 (jobs-radar; contact anasnasir2208@gmail.com)"}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def clean(text, limit=700):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", html.unescape(str(text)))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def relevant(title, tags=""):
    t = " " + (title or "").lower() + " "
    if any(n in t for n in NEGATIVE):
        return False
    return any(k in t for k in KEYWORDS)


def norm(job):
    """Standard shape for every source."""
    return {
        "title": job["title"], "company": job.get("company", ""),
        "location": job.get("location", "Remote"), "url": job["url"],
        "source": job["source"], "date": job.get("date", ""),
        "tags": job.get("tags", ""), "description": clean(job.get("description", "")),
    }


def from_remotive():
    out = []
    for term in ["copywriter", "email marketing", "content marketing", "marketing", "creative strategist"]:
        try:
            r = requests.get(f"https://remotive.com/api/remote-jobs?search={term}", headers=UA, timeout=30)
            for j in r.json().get("jobs", []):
                out.append({"title": j.get("title", ""), "company": j.get("company_name", ""),
                            "location": j.get("candidate_required_location", "Remote"),
                            "url": j.get("url", ""), "source": "Remotive",
                            "date": (j.get("publication_date") or "")[:10],
                            "tags": " ".join(j.get("tags", [])), "description": j.get("description", "")})
        except Exception as e:
            print(f"  ❌ Remotive({term}): {e}")
    return out


def from_jobicy():
    out = []
    for tag in ["copywriting", "marketing", "content", "seo"]:
        try:
            r = requests.get(f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={tag}", headers=UA, timeout=30)
            for j in r.json().get("jobs", []):
                out.append({"title": j.get("jobTitle", ""), "company": j.get("companyName", ""),
                            "location": j.get("jobGeo", "Remote"), "url": j.get("url", ""),
                            "source": "Jobicy", "date": (j.get("pubDate") or "")[:10],
                            "tags": " ".join(j.get("jobIndustry", []) if isinstance(j.get("jobIndustry"), list) else []),
                            "description": j.get("jobExcerpt", "")})
        except Exception as e:
            print(f"  ❌ Jobicy({tag}): {e}")
    return out


def from_arbeitnow():
    out = []
    try:
        r = requests.get("https://www.arbeitnow.com/api/job-board-api", headers=UA, timeout=30)
        for j in r.json().get("data", []):
            out.append({"title": j.get("title", ""), "company": j.get("company_name", ""),
                        "location": j.get("location", "Remote"), "url": j.get("url", ""),
                        "source": "Arbeitnow", "date": "",
                        "tags": " ".join(j.get("tags", []) + j.get("job_types", [])),
                        "description": j.get("description", "")})
    except Exception as e:
        print(f"  ❌ Arbeitnow: {e}")
    return out


def from_remoteok():
    out = []
    try:
        r = requests.get("https://remoteok.com/api", headers=UA, timeout=30)
        for j in r.json():
            if not isinstance(j, dict) or "position" not in j:
                continue
            out.append({"title": j.get("position", ""), "company": j.get("company", ""),
                        "location": j.get("location", "Remote"), "url": j.get("url", ""),
                        "source": "RemoteOK", "date": (j.get("date") or "")[:10],
                        "tags": " ".join(j.get("tags", [])), "description": j.get("description", "")})
    except Exception as e:
        print(f"  ❌ RemoteOK: {e}")
    return out


def main():
    print("💼 Anas Jobs Radar — scanning free job boards\n")
    seen = set(load_json(SEEN_FILE, []))
    raw = from_remotive() + from_jobicy() + from_arbeitnow() + from_remoteok()
    print(f"📦 {len(raw)} raw postings pulled\n")

    jobs, ids = [], set()
    for j in raw:
        if not j.get("url") or not j.get("title"):
            continue
        if not relevant(j["title"], j.get("tags", "")):
            continue
        jid = j["url"]
        if jid in seen or jid in ids:
            continue
        ids.add(jid)
        jobs.append(norm(j))
        print(f"✅ {j['source']:<9} {j['title'][:55]}  @ {j.get('company','')[:24]}")

    jobs = jobs[:30]  # keep the pack tight for the brain
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=4, ensure_ascii=False)
    seen.update(j["url"] for j in jobs)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)

    print(f"\n✅ {len(jobs)} new relevant jobs saved to {RAW_FILE}")


if __name__ == "__main__":
    main()

import os
import re
import sys
import json
import html
import email.utils
from collections import defaultdict
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
        "job_type": job.get("job_type", ""), "salary": job.get("salary", ""),
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
                            "job_type": j.get("job_type", ""), "salary": j.get("salary", ""),
                            "tags": ", ".join(j.get("tags", [])), "description": j.get("description", "")})
        except Exception as e:
            print(f"  ❌ Remotive({term}): {e}")
    return out


def from_jobicy():
    out = []
    for tag in ["copywriting", "marketing", "content", "seo"]:
        try:
            r = requests.get(f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={tag}", headers=UA, timeout=30)
            for j in r.json().get("jobs", []):
                smin, smax, cur = j.get("annualSalaryMin"), j.get("annualSalaryMax"), j.get("salaryCurrency", "")
                salary = f"{cur} {int(smin):,}–{int(smax):,}/yr" if smin and smax else ""
                jt = j.get("jobType", [])
                out.append({"title": j.get("jobTitle", ""), "company": j.get("companyName", ""),
                            "location": j.get("jobGeo", "Remote"), "url": j.get("url", ""),
                            "source": "Jobicy", "date": (j.get("pubDate") or "")[:10],
                            "job_type": ", ".join(jt) if isinstance(jt, list) else str(jt or ""),
                            "salary": salary,
                            "tags": ", ".join(j.get("jobIndustry", []) if isinstance(j.get("jobIndustry"), list) else []),
                            "description": j.get("jobExcerpt", "")})
        except Exception as e:
            print(f"  ❌ Jobicy({tag}): {e}")
    return out


def from_arbeitnow():
    out = []
    try:
        r = requests.get("https://www.arbeitnow.com/api/job-board-api", headers=UA, timeout=30)
        for j in r.json().get("data", []):
            date = ""
            try:
                ts = j.get("created_at")
                if ts:
                    date = datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                pass
            out.append({"title": j.get("title", ""), "company": j.get("company_name", ""),
                        "location": j.get("location", "Remote"), "url": j.get("url", ""),
                        "source": "Arbeitnow", "date": date,
                        "job_type": ", ".join(j.get("job_types", [])), "salary": "",
                        "tags": ", ".join(j.get("tags", [])),
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
            smin, smax = j.get("salary_min"), j.get("salary_max")
            salary = f"${int(smin):,}–${int(smax):,}" if smin and smax else ""
            out.append({"title": j.get("position", ""), "company": j.get("company", ""),
                        "location": j.get("location", "Remote"), "url": j.get("url", ""),
                        "source": "RemoteOK", "date": (j.get("date") or "")[:10],
                        "job_type": "", "salary": salary,
                        "tags": ", ".join(j.get("tags", [])), "description": j.get("description", "")})
    except Exception as e:
        print(f"  ❌ RemoteOK: {e}")
    return out


def from_weworkremotely():
    out = []
    for cat in ["remote-marketing-jobs", "remote-copywriting-jobs", "remote-sales-and-marketing-jobs"]:
        try:
            r = requests.get(f"https://weworkremotely.com/categories/{cat}.rss", headers=UA, timeout=30)
            for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
                def g(tag):
                    m = re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S)
                    if not m:
                        return ""
                    return re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.S).strip()
                pub, date = g("pubDate"), ""
                try:
                    if pub:
                        date = email.utils.parsedate_to_datetime(pub).strftime("%Y-%m-%d")
                except Exception:
                    pass
                title_raw = g("title")
                company, sep, jt = title_raw.partition(":")
                out.append({"title": (jt or title_raw).strip(), "company": company.strip() if sep else "",
                            "location": g("region") or "Remote", "url": g("link"),
                            "source": "WeWorkRemotely", "date": date, "job_type": "", "salary": "",
                            "tags": g("category"), "description": g("description")})
        except Exception as e:
            print(f"  ❌ WWR({cat}): {e}")
    return out


def is_recent(ds, max_days=1):
    # Only genuinely FRESH jobs: posted today or yesterday. If a posting has no
    # verifiable date we can't prove it's fresh, so we drop it (better empty than stale).
    if not ds:
        return False
    try:
        d = datetime.strptime(ds, "%Y-%m-%d").date()
        return 0 <= (datetime.now(timezone.utc).date() - d).days <= max_days
    except Exception:
        return False


def main():
    print("💼 Anas Jobs Radar — scanning free job boards\n")
    seen = set(load_json(SEEN_FILE, []))
    raw = (from_remotive() + from_jobicy() + from_arbeitnow()
           + from_remoteok() + from_weworkremotely())
    print(f"📦 {len(raw)} raw postings pulled from 5 sites\n")

    jobs, ids = [], set()
    for j in raw:
        if not j.get("url") or not j.get("title"):
            continue
        if not relevant(j["title"], j.get("tags", "")):
            continue
        jid = j["url"]
        if jid in seen or jid in ids:
            continue
        nj = norm(j)
        if not is_recent(nj["date"]):     # drop stale postings
            continue
        ids.add(jid)
        jobs.append(nj)

    # freshest first, then cap per source so no single website dominates the list
    jobs.sort(key=lambda x: x.get("date", ""), reverse=True)
    per_src, balanced = defaultdict(int), []
    for jb in jobs:
        if per_src[jb["source"]] >= 8:
            continue
        per_src[jb["source"]] += 1
        balanced.append(jb)
    jobs = balanced[:32]

    for jb in jobs:
        print(f"✅ {jb['source']:<14} {jb['date'] or '(no date) ':<11} {jb['title'][:44]}")

    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=4, ensure_ascii=False)
    seen.update(j["url"] for j in jobs)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)

    dist = {}
    for jb in jobs:
        dist[jb["source"]] = dist.get(jb["source"], 0) + 1
    print(f"\n✅ {len(jobs)} jobs saved · sources: {dist}")


if __name__ == "__main__":
    from runstate import run_once
    run_once("jobs_module", main)

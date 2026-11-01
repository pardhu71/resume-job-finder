"""RoleRoute v3: public vacancy adapters + inspectable, non-LLM matching.

Only fixed public GET APIs are contacted. No resume content or personal details
are sent to job sources. Scores are heuristics, not hiring or eligibility odds.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import urlparse, urlunparse

import requests

from analyzer import find_skills

# Boards verified as publicly indexed in 2026. Boards may change/vanish.
# These are starting sources, not a complete job search index.
DEFAULT_BOARDS: dict[str, dict[str, str]] = {
    "India": {
        "aidashinc": "AiDASH",
        "sigmoid": "Sigmoid",
        "tide": "Tide",
        "purestorage": "Everpure",
        "instead": "Instead",
        "zyngacareers": "Zynga",
    },
    "International": {
        "figma": "Figma",
        "ramp": "Ramp",
        "galaxydigitalservices": "Galaxy",
    },
}
_ALLOWED_BOARD = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,49}$")
_TIMEOUT = (4, 15)
_MAX_JOBS_PER_BOARD = 200
_MAX_REMOTE = 200
_MAX_RESPONSE = 12 * 1024 * 1024
INDIAN_CITIES = (
    "bengaluru", "bangalore", "hyderabad", "chennai", "pune", "mumbai", "delhi",
    "noida", "gurugram", "gurgaon", "kolkata", "kochi", "ahmedabad", "jaipur",
    "visakhapatnam", "vizag", "bhubaneswar", "coimbatore", "trivandrum",
)
SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|director|head of|vice president|vp|lead|manager|chief)\b",
    re.IGNORECASE,
)
ENTRY_TITLE = re.compile(r"\b(intern|internship|trainee|graduate|fresher|entry.level|junior|associate)\b", re.I)


class JobSourceError(Exception):
    """Recoverable provider failure with no sensitive error detail."""


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_html(value: str) -> str:
    parser = _HTMLText()
    try:
        parser.feed(value[:100_000])
        return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()[:24_000]
    except Exception:
        return re.sub(r"<[^>]+>", " ", value[:100_000])[:24_000]


def board_name(name: str) -> str:
    value = name.strip()
    if not _ALLOWED_BOARD.fullmatch(value):
        raise JobSourceError("Board ID must be 2–50 letters, numbers, dashes or underscores.")
    return value


def parse_board_names(text: str, limit: int = 4) -> list[str]:
    names: list[str] = []
    for raw in text.split(","):
        if raw.strip():
            value = board_name(raw)
            if value.lower() not in [n.lower() for n in names]:
                names.append(value)
    if len(names) > limit:
        raise JobSourceError(f"At most {limit} additional boards are allowed.")
    return names


def valid_job_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = urlparse(value)
        return url.scheme == "https" and bool(url.hostname) and not url.username and not url.password
    except (ValueError, TypeError):
        return False


def canonical_url(value: str) -> str:
    try:
        parts = urlparse(value)
        return urlunparse((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", "", ""))
    except (ValueError, TypeError):
        return value


@dataclass(frozen=True)
class JobListing:
    source: str
    company: str
    job_id: str
    title: str
    location: str
    description: str
    url: str
    last_updated: str = ""
    is_remote: bool = False
    candidate_location: str = ""  # Explicit region restrictions when provider supplies them


@dataclass(frozen=True)
class JobMatch:
    job: JobListing
    score: int
    matching_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    title_score: int
    required_years: int | None
    experience_note: str
    location_note: str
    remote_eligibility: str


def _get_json(url: str, params: dict[str, str | int]) -> dict | list:
    # This is only called with URLs composed from hard-coded API hosts.
    try:
        response = requests.get(
            url, params=params, timeout=_TIMEOUT, allow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "RoleRoute-Job-Finder/0.3"},
            stream=True,
        )
        with response:
            response.raise_for_status()
            if response.status_code != 200:
                raise JobSourceError("The job source did not return a usable response.")
            body = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                body.extend(chunk)
                if len(body) > _MAX_RESPONSE:
                    raise JobSourceError("Job source response exceeded the size limit.")
            return json.loads(body)
    except JobSourceError:
        raise
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise JobSourceError("Could not retrieve this job source right now.") from exc


def fetch_greenhouse_jobs(board: str) -> list[JobListing]:
    board = board_name(board)
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", {"content": "true"})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise JobSourceError("Unexpected data from Greenhouse.")
    result: list[JobListing] = []
    for item in data["jobs"][:_MAX_JOBS_PER_BOARD]:
        if not isinstance(item, dict) or item.get("internal_job_id", 1) is None:
            continue
        url, title = item.get("absolute_url"), item.get("title")
        if not valid_job_url(url) or not isinstance(title, str) or not title.strip():
            continue
        loc = item.get("location")
        location = str(loc.get("name", "Unknown")) if isinstance(loc, dict) else "Unknown"
        result.append(JobListing(
            source="Greenhouse", company=DEFAULT_BOARDS["India"].get(board, DEFAULT_BOARDS["International"].get(board, board)),
            job_id=str(item.get("id") or ""), title=title.strip(), location=location,
            description=clean_html(str(item.get("content") or "")), url=url,
            last_updated=str(item.get("updated_at") or "")[:10],
            is_remote=bool(re.search(r"\bremote\b", location, re.I)),
        ))
    return result


def fetch_lever_jobs(board: str) -> list[JobListing]:
    board = board_name(board)
    data = _get_json(f"https://api.lever.co/v0/postings/{board}", {"mode": "json", "limit": _MAX_JOBS_PER_BOARD})
    if not isinstance(data, list):
        raise JobSourceError("Unexpected data from Lever.")
    result: list[JobListing] = []
    for item in data[:_MAX_JOBS_PER_BOARD]:
        if not isinstance(item, dict):
            continue
        url, title = item.get("hostedUrl"), item.get("text")
        if not valid_job_url(url) or not isinstance(title, str) or not title.strip():
            continue
        categories = item.get("categories") or {}
        location = str(categories.get("location", "Unknown")) if isinstance(categories, dict) else "Unknown"
        desc = str(item.get("descriptionPlain") or "") or clean_html(str(item.get("description") or ""))
        result.append(JobListing(
            source="Lever", company=board, job_id=str(item.get("id") or ""),
            title=title.strip(), location=location, description=desc[:24_000], url=url,
            is_remote=bool(re.search(r"\bremote\b", location, re.I)) or (
                isinstance(categories, dict) and "remote" in str(categories.get("workplaceType", "")).lower()
            ),
        ))
    return result


def fetch_remotive_jobs() -> list[JobListing]:
    """Remotive public feed. Host app must cache >=6h; attribution is mandatory."""
    data = _get_json("https://remotive.com/api/remote-jobs", {"limit": _MAX_REMOTE})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise JobSourceError("Unexpected data from Remotive.")
    result: list[JobListing] = []
    for item in data["jobs"][:_MAX_REMOTE]:
        if not isinstance(item, dict):
            continue
        url, title = item.get("url"), item.get("title")
        if not valid_job_url(url) or not isinstance(title, str) or not title.strip():
            continue
        eligibility = str(item.get("candidate_required_location") or "Not specified")
        result.append(JobListing(
            source="Remotive", company=str(item.get("company_name") or "Unknown employer")[:120],
            job_id=str(item.get("id") or ""), title=title.strip(),
            location=f"Remote · {eligibility}", candidate_location=eligibility,
            description=clean_html(str(item.get("description") or "")), url=url,
            last_updated=str(item.get("publication_date") or "")[:10], is_remote=True,
        ))
    return result


def location_is_india(location: str) -> bool:
    value = location.lower()
    if re.search(r"\b(india|indian|in-based|in office india)\b", value):
        return True
    return any(re.search(r"\b" + re.escape(city) + r"\b", value) for city in INDIAN_CITIES)


def remote_eligibility(job: JobListing) -> str:
    """For an India-based applicant: supported / restricted / unknown / not-remote.

    This is only a quick location hint. Visas, timezones and other rules vary.
    """
    if not job.is_remote:
        return "Not remote"
    restriction = (job.candidate_location or job.location).lower()
    if any(word in restriction for word in ("worldwide", "anywhere", "global", "world wide")):
        return "Worldwide stated; verify conditions"
    if location_is_india(restriction) or re.search(r"\b(asia|apac)\b", restriction):
        return "May allow India; verify conditions"
    if re.search(r"\b(?:united states|usa|u\.?s\.?|us only|uk only|europe|emea|canada|australia)\b", restriction):
        return "Geographically restricted; check eligibility"
    if job.candidate_location and job.candidate_location.lower() not in ("not specified", "remote"):
        return "Geographically restricted; check eligibility"
    return "Region not confirmed"


def chosen_scope(job: JobListing, scopes: set[str]) -> bool:
    if job.is_remote:
        if "Remote" in scopes:
            return True
        return "India" in scopes and remote_eligibility(job).startswith(("Worldwide", "May allow India"))
    if location_is_india(job.location):
        return "India" in scopes
    if job.location.strip().lower() in ("unknown", "", "multiple locations"):
        return "International" in scopes  # location genuinely unknown, flagged in UI
    return "International" in scopes


def location_text_matches(location: str, city: str) -> bool:
    if not city.strip():
        return True
    term = city.strip().lower()
    loc = location.lower()
    if term in ("bengaluru", "bangalore"):
        return "bengaluru" in loc or "bangalore" in loc
    return term in loc


def min_experience_years(text: str) -> int | None:
    """Conservative phrase extraction; may miss or misinterpret requirements."""
    excerpt = text[:20_000]
    patterns = (
        r"\b(?:at least|minimum of|minimum|min\.?|over)\s+(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:[a-z-]+\s+){0,3}experience\b",
        r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+of\s+(?:\w+[ -]+){0,5}experience\b",
        r"\b(?:experience|exp)\s*(?:required|needed)?\s*[:\-]?\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b",
        r"\b(\d{1,2})\s*[-–]\s*\d{1,2}\s*(?:years?|yrs?)\s+of\s+(?:\w+\s+){0,3}experience\b",
        r"\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b",
    )
    matches = [int(match.group(1)) for pat in patterns for match in re.finditer(pat, excerpt, re.I)]
    return max(matches) if matches else None


def title_relevance(title: str, roles: list[str]) -> float:
    if not roles:
        return 0.0
    stop = {"junior", "senior", "entry", "level", "intern", "internship", "lead", "remote", "ii", "iii", "and", "the", "of"}
    def tok(s: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", s.lower())) - stop
    jobwords = tok(title)
    if not jobwords:
        return 0.0
    best = 0.0
    for role in roles:
        words = tok(role)
        if words:
            overlap = len(jobwords & words) / len(words)
            sim = SequenceMatcher(None, " ".join(sorted(jobwords)), " ".join(sorted(words))).ratio()
            best = max(best, overlap, sim * 0.6)
    return min(best, 1.0)


def match_jobs(
    jobs: list[JobListing], skills: list[str], roles: list[str], *,
    scopes: set[str] | None = None, years_experience: int = 0,
    strict_experience: bool = True, preferred_city: str = "", strict_city: bool = False,
    limit: int = 30, exploratory: bool = False,
) -> list[JobMatch]:
    """Ranking with title/skill/experience/location signals; not an eligibility decision."""
    scopes = scopes if scopes is not None else {"India", "International", "Remote"}
    have = set(skills)
    results: list[JobMatch] = []
    seen_urls: set[str] = set()
    for job in jobs:
        unique = canonical_url(job.url)
        if unique in seen_urls:
            continue
        seen_urls.add(unique)
        if not chosen_scope(job, scopes):
            continue
        city_ok = location_text_matches(job.location, preferred_city)
        if strict_city and preferred_city and not city_ok:
            continue

        requested = min_experience_years(job.description)
        looks_senior = bool(SENIOR_TITLE.search(job.title))
        if strict_experience and requested is not None and requested > years_experience:
            continue
        if strict_experience and years_experience < 2 and looks_senior:
            continue

        title_ratio = title_relevance(job.title, roles)
        listed = set(find_skills(job.description + " " + job.title))
        matching = sorted(listed & have)
        missing = sorted(listed - have)
        if exploratory:
            # Exploratory discovery: keep at least one skill signal or a weak title signal.
            # These are not reliable fits and must be labeled separately in the UI.
            if title_ratio < 0.20 and not matching:
                continue
        elif title_ratio < 0.28 and len(matching) < 2:
            continue

        skill_ratio = len(matching) / len(listed) if listed else 0
        if requested is not None:
            exp_ratio = 1.0 if years_experience >= requested else 0.0
            exp_note = f"Detected minimum around {requested} year(s); verify job description"
        elif looks_senior:
            exp_ratio = 0.1 if years_experience < 4 else 0.6
            exp_note = "Senior title; requirements must be checked"
        else:
            exp_ratio = 0.5  # Lack of explicit min years does NOT mean fresher-friendly.
            exp_note = "Minimum experience not reliably detected; check requirements"

        if preferred_city:
            loc_ratio = 1 if city_ok else 0
            loc_note = "Preferred location mentioned" if city_ok else "Preferred city not mentioned"
        elif job.is_remote:
            loc_ratio = 0.6
            loc_note = "Remote listing; location restrictions may apply"
        else:
            loc_ratio = 0.5
            loc_note = "Location not compared with a city preference"

        score = round(40 * title_ratio + 35 * skill_ratio + 15 * exp_ratio + 10 * loc_ratio)
        if requested is not None and years_experience < requested:
            score = min(score, 49)
        if looks_senior and years_experience < 2:
            score = min(score, 45)
        eligibility = remote_eligibility(job)
        if job.is_remote and eligibility == "Geographically restricted; check eligibility":
            score = min(score, 65)
        results.append(JobMatch(
            job=job, score=max(0, min(100, score)),
            matching_skills=tuple(matching), missing_skills=tuple(missing[:8]),
            title_score=round(100 * title_ratio), required_years=requested,
            experience_note=exp_note, location_note=loc_note, remote_eligibility=eligibility,
        ))
    results.sort(key=lambda match: (-match.score, -len(match.matching_skills), match.job.title.lower()))
    return results[:limit]


def matching_diagnostics(
    jobs: list[JobListing], skills: list[str], roles: list[str], *,
    scopes: set[str] | None = None, years_experience: int = 0,
    strict_experience: bool = True, preferred_city: str = "", strict_city: bool = False,
) -> dict[str, int]:
    """Count how many distinct postings survive each stage of the same hard filters.

    Counts are sequential, so each stage can explain a zero-match result.
    They are not eligibility estimates.
    """
    scopes = scopes if scopes is not None else {"India", "International", "Remote"}
    counts = {
        "retrieved": len(jobs), "unique": 0, "region": 0,
        "city": 0, "experience": 0, "relevance": 0, "exploratory": 0,
    }
    seen: set[str] = set()
    have = set(skills)
    for job in jobs:
        key = canonical_url(job.url)
        if key in seen:
            continue
        seen.add(key)
        counts["unique"] += 1
        if not chosen_scope(job, scopes):
            continue
        counts["region"] += 1
        if strict_city and preferred_city and not location_text_matches(job.location, preferred_city):
            continue
        counts["city"] += 1
        requested = min_experience_years(job.description)
        looks_senior = bool(SENIOR_TITLE.search(job.title))
        if strict_experience and (
            (requested is not None and requested > years_experience)
            or (years_experience < 2 and looks_senior)
        ):
            continue
        counts["experience"] += 1
        title_ratio = title_relevance(job.title, roles)
        matching = set(find_skills(job.description + " " + job.title)) & have
        if title_ratio >= 0.28 or len(matching) >= 2:
            counts["relevance"] += 1
        if title_ratio >= 0.20 or bool(matching):
            counts["exploratory"] += 1
    return counts

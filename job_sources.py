"""Public employer job-board adapters and transparent heuristic matching.

Uses only employer public GET feeds; never submits applicant data or resumes.
It does NOT discover every job or establish eligibility for a position.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

from analyzer import find_skills

_ALLOWED_BOARD = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,49}$")
_TIMEOUT = (4, 12)
_MAX_JOBS_PER_BOARD = 200


class JobSourceError(Exception):
    """Recoverable source error to show the user without an internal traceback."""


class _StripTags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_html(value: str) -> str:
    parser = _StripTags()
    try:
        parser.feed(value[:80_000])
        return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()[:30_000]
    except Exception:
        return re.sub(r"<[^>]+>", " ", value)[:30_000]


def board_name(value: str) -> str:
    value = value.strip()
    if not _ALLOWED_BOARD.fullmatch(value):
        raise JobSourceError("Board ID must use 2–50 letters, numbers, hyphens, or underscores.")
    return value


def parse_board_names(text: str, limit: int = 5) -> list[str]:
    values = [part.strip() for part in text.split(",") if part.strip()]
    unique: list[str] = []
    for value in values:
        validated = board_name(value)
        if validated.lower() not in {item.lower() for item in unique}:
            unique.append(validated)
    if len(unique) > limit:
        raise JobSourceError(f"Please use at most {limit} boards for each provider.")
    return unique


def valid_job_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
    except (ValueError, TypeError):
        return False


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


@dataclass(frozen=True)
class JobMatch:
    job: JobListing
    score: int
    matching_skills: tuple[str, ...]
    job_skills: tuple[str, ...]
    role_relevance: int
    location_matches: bool


def _get_json(url: str, params: dict[str, str | int]) -> dict | list:
    try:
        response = requests.get(
            url,
            params=params,
            timeout=_TIMEOUT,
            headers={"Accept": "application/json", "User-Agent": "RoleRoute-Job-Finder/0.2"},
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise JobSourceError(f"Job board replied with status {response.status_code}.")
        if len(response.content) > 12 * 1024 * 1024:
            raise JobSourceError("This employer's job list is too large for the prototype.")
        return response.json()
    except JobSourceError:
        raise
    except (requests.RequestException, ValueError) as exc:
        raise JobSourceError("Could not retrieve this employer's job board right now.") from exc


def fetch_greenhouse_jobs(company: str) -> list[JobListing]:
    """Fetch currently published posts exposed by an employer's Greenhouse board."""
    company = board_name(company)
    data = _get_json(
        f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs",
        {"content": "true"},
    )
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise JobSourceError("Unexpected data from Greenhouse.")
    jobs: list[JobListing] = []
    for item in data["jobs"][:_MAX_JOBS_PER_BOARD]:
        if not isinstance(item, dict) or item.get("internal_job_id", 1) is None:
            continue  # Exclude general interest / prospect postings.
        url = item.get("absolute_url", "")
        if not isinstance(url, str) or not valid_job_url(url):
            continue
        name = item.get("title")
        if not isinstance(name, str) or not name.strip():
            continue
        location = item.get("location", {})
        location_str = location.get("name", "Unknown") if isinstance(location, dict) else "Unknown"
        jobs.append(
            JobListing(
                source="Greenhouse",
                company=company,
                job_id=str(item.get("id", "")),
                title=name.strip(),
                location=str(location_str),
                description=clean_html(str(item.get("content") or "")),
                url=url,
                last_updated=str(item.get("updated_at") or "")[:10],
            )
        )
    return jobs


def fetch_lever_jobs(company: str) -> list[JobListing]:
    company = board_name(company)
    data = _get_json(
        f"https://api.lever.co/v0/postings/{company}",
        {"mode": "json", "limit": _MAX_JOBS_PER_BOARD},
    )
    if not isinstance(data, list):
        raise JobSourceError("Unexpected data from Lever.")
    jobs: list[JobListing] = []
    for item in data[:_MAX_JOBS_PER_BOARD]:
        if not isinstance(item, dict):
            continue
        url = item.get("hostedUrl", "")
        if not isinstance(url, str) or not valid_job_url(url):
            continue
        title = item.get("text")
        if not isinstance(title, str) or not title.strip():
            continue
        categories = item.get("categories") or {}
        location = categories.get("location", "Unknown") if isinstance(categories, dict) else "Unknown"
        description = str(item.get("descriptionPlain") or "")
        if not description:
            description = clean_html(str(item.get("description") or ""))
        jobs.append(
            JobListing(
                source="Lever",
                company=company,
                job_id=str(item.get("id") or ""),
                title=title.strip(),
                location=str(location),
                description=description[:30_000],
                url=url,
            )
        )
    return jobs


def _title_overlap(title: str, expected_roles: list[str]) -> float:
    if not expected_roles:
        return 0.0
    def tokens(value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", value.lower())) - {
            "junior", "senior", "entry", "level", "intern", "lead", "remote", "ii", "iii",
        }
    job_words = tokens(title)
    if not job_words:
        return 0.0
    best = 0.0
    for role in expected_roles:
        role_words = tokens(role)
        if not role_words:
            continue
        overlap = len(job_words & role_words) / len(role_words)
        similarity = SequenceMatcher(None, " ".join(sorted(job_words)), " ".join(sorted(role_words))).ratio()
        best = max(best, overlap, similarity * 0.65)
    return min(best, 1.0)


def match_jobs(
    jobs: list[JobListing],
    resume_skills: list[str],
    suitable_roles: list[str],
    location: str = "",
    entry_level_only: bool = False,
    filter_location: bool = False,
    limit: int = 25,
) -> list[JobMatch]:
    """Return explainable, approximate relevance scores, NOT hiring probabilities."""
    resume_set = set(resume_skills)
    location_filter = location.strip().lower()
    results: list[JobMatch] = []
    seen: set[str] = set()
    for job in jobs:
        if job.url in seen:
            continue
        seen.add(job.url)
        if entry_level_only and re.search(r"\b(senior|staff|principal|director|head of|vp|lead)\b", job.title, re.I):
            continue
        location_matches = bool(location_filter and location_filter in job.location.lower())
        if filter_location and location_filter and not location_matches:
            continue
        title_relevance = _title_overlap(job.title, suitable_roles)
        # Only check terms mentioned in source listings; a listed term need not be required.
        job_skills = set(find_skills(job.title + " " + job.description))
        matched = sorted(job_skills & resume_set)
        skill_relevance = len(matched) / max(1, len(job_skills)) if job_skills else 0.0
        if title_relevance < 0.28 and len(matched) < 2:
            continue  # No meaningful title relevance or multiple skill signals.
        score = round(65 * title_relevance + 30 * skill_relevance + (5 if location_matches else 0))
        results.append(
            JobMatch(
                job=job,
                score=min(score, 100),
                matching_skills=tuple(matched),
                job_skills=tuple(sorted(job_skills)),
                role_relevance=round(title_relevance * 100),
                location_matches=location_matches,
            )
        )
    results.sort(key=lambda result: (-result.score, -len(result.matching_skills), result.job.title))
    return results[:limit]

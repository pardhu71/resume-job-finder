"""Simple, deterministic resume signals for an educational MVP.

This module is not an AI model and does not determine hiring eligibility.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from urllib.parse import quote_plus

from docx import Document
from pypdf import PdfReader

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 30
MAX_TEXT_CHARS = 100_000

# Pattern lists intentionally include common spelling variants. Add and validate
# more terms with user feedback; a keyword's presence does not establish mastery.
SKILL_PATTERNS: dict[str, tuple[str, ...]] = {
    "Python": (r"\bpython\b",),
    "SQL": (r"\bsql\b", r"\bmysql\b", r"\bpostgresql\b", r"\bpostgres\b"),
    "Excel": (r"\bexcel\b", r"\bspreadsheets?\b"),
    "Power BI": (r"\bpower\s*bi\b",),
    "Tableau": (r"\btableau\b",),
    "Pandas": (r"\bpandas\b",),
    "NumPy": (r"\bnumpy\b",),
    "Machine Learning": (r"\bmachine learning\b", r"\bml models?\b"),
    "Statistics": (r"\bstatistics?\b", r"\bstatistical\b"),
    "Java": (r"\bjava\b(?!\s*script)",),
    "JavaScript": (r"\bjavascript\b", r"\bjs\b"),
    "TypeScript": (r"\btypescript\b",),
    "HTML": (r"\bhtml\b",),
    "CSS": (r"\bcss\b",),
    "React": (r"\breact(?:\.js|js)?\b",),
    "Node.js": (r"\bnode(?:\.js|js)?\b",),
    "Django": (r"\bdjango\b",),
    "Flask": (r"\bflask\b",),
    "REST APIs": (r"\brest(?:ful)?\s*apis?\b", r"\bapi integration\b"),
    "Git": (r"\bgit\b", r"\bgithub\b", r"\bgitlab\b"),
    "Docker": (r"\bdocker\b",),
    "Kubernetes": (r"\bkubernetes\b", r"\bk8s\b"),
    "AWS": (r"\baws\b", r"\bamazon web services\b"),
    "Azure": (r"\bazure\b",),
    "Linux": (r"\blinux\b",),
    "Figma": (r"\bfigma\b",),
    "UX Research": (r"\bux research\b", r"\buser research\b"),
    "Wireframing": (r"\bwireframes?\b", r"\bwireframing\b"),
    "SEO": (r"\bseo\b", r"\bsearch engine optimi[sz]ation\b"),
    "Social Media Marketing": (r"\bsocial media marketing\b",),
    "Google Analytics": (r"\bgoogle analytics\b", r"\bga4\b"),
    "Project Management": (r"\bproject management\b",),
    "Communication": (r"\bcommunication skills?\b",),
}

ROLE_SKILLS: dict[str, tuple[str, ...]] = {
    "Junior Data Analyst": ("Excel", "SQL", "Python", "Power BI", "Tableau"),
    "Python Developer": ("Python", "Git", "Django", "Flask", "REST APIs"),
    "Frontend Developer": ("HTML", "CSS", "JavaScript", "React", "TypeScript"),
    "Backend Developer": ("Python", "Java", "Node.js", "SQL", "REST APIs"),
    "Business Analyst": ("Excel", "SQL", "Power BI", "Communication", "Project Management"),
    "Junior Data Scientist": ("Python", "Pandas", "NumPy", "Statistics", "Machine Learning"),
    "DevOps / Cloud Engineer": ("Linux", "Git", "Docker", "Kubernetes", "AWS", "Azure"),
    "UI/UX Designer": ("Figma", "UX Research", "Wireframing"),
    "Digital Marketing Specialist": ("SEO", "Social Media Marketing", "Google Analytics"),
}


@dataclass(frozen=True)
class RoleSuggestion:
    title: str
    found: tuple[str, ...]
    missing: tuple[str, ...]
    coverage_pct: int


def extract_resume_text(data: bytes, filename: str) -> str:
    """Extract text from a supported resume without writing it to disk."""
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Please upload a resume smaller than 5 MB.")

    suffix = filename.lower().rsplit(".", 1)[-1]
    try:
        if suffix == "pdf":
            reader = PdfReader(io.BytesIO(data), strict=False)
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ValueError("Please use a PDF with 30 pages or fewer.")
            parts = [(page.extract_text() or "") for page in reader.pages]
            text = "\n".join(parts)
        elif suffix == "docx":
            document = Document(io.BytesIO(data))
            parts = [p.text for p in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(parts)
        else:
            raise ValueError("Only .pdf and .docx resumes are supported.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "This file could not be read. Try another PDF or DOCX. "
            "Scanned/image-only PDFs are not supported in version 1."
        ) from exc

    clean = re.sub(r"[ \t]+", " ", text).strip()
    if not clean:
        raise ValueError(
            "We couldn't extract readable text. Scanned/image-only PDFs "
            "need OCR, which is not included in version 1."
        )
    return clean[:MAX_TEXT_CHARS]


def find_skills(text: str) -> list[str]:
    return [
        skill
        for skill, patterns in SKILL_PATTERNS.items()
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    ]


def suggest_roles(skills: list[str], limit: int = 5) -> list[RoleSuggestion]:
    have = set(skills)
    results: list[RoleSuggestion] = []
    for role, desired in ROLE_SKILLS.items():
        found = tuple(x for x in desired if x in have)
        if not found:
            continue
        missing = tuple(x for x in desired if x not in have)
        results.append(
            RoleSuggestion(
                title=role,
                found=found,
                missing=missing,
                coverage_pct=round(len(found) / len(desired) * 100),
            )
        )
    # Role ordering is a simple heuristic; it is not a hiring recommendation.
    return sorted(results, key=lambda r: (-r.coverage_pct, -len(r.found), r.title))[:limit]


def google_job_search_url(role: str, location: str = "", seniority: str = "") -> str:
    """Build an ordinary Google search, not a verified listing or a data API."""
    terms = [role, "jobs"]
    if seniority == "Fresher / entry-level":
        terms.append("entry level OR fresher")
    elif seniority == "1–3 years":
        terms.append("junior")
    elif seniority == "4+ years":
        terms.append("experienced")
    if location.strip():
        terms.append(location.strip()[:80])
    return "https://www.google.com/search?q=" + quote_plus(" ".join(terms))

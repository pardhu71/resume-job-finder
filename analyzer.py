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
    "C": (r"(?<![a-zA-Z0-9+])c\s+(?:programming|language|developer|coding)", r"\bembedded\s+c\b"),
    "C++": (r"(?<![a-zA-Z0-9])c\+\+(?![a-zA-Z0-9])", r"\bcpp\b"),
    "Embedded Systems": (r"\bembedded\s+(?:systems?|software|development|programming|applications?)\b",),
    "Firmware": (r"\bfirmware\b",),
    "Microcontrollers": (r"\bmicrocontrollers?\b", r"\bmcu\b"),
    "STM32": (r"\bstm32[a-z0-9]*\b",),
    "ESP32": (r"\besp32\b",),
    "Arduino": (r"\barduino\b",),
    "RTOS": (r"\brtos\b", r"\bfree\s?rtos\b", r"\bzephyr\s+rtos\b"),
    "UART": (r"\buart\b",),
    "SPI": (r"\bspi\b",),
    "I2C": (r"\bi2c\b", r"\biic\b"),
    "CAN Bus": (r"\bcan\s*(?:bus|protocol|fd)\b",),
    "Embedded Linux": (r"\bembedded\s+linux\b",),
    "Device Drivers": (r"\bdevice\s+drivers?\b", r"\blinux\s+kernel\s+drivers?\b"),
    "PCB Design": (r"\bpcb(?:\s+design|\s+layout)?\b",),
    "FPGA": (r"\bfpga\b", r"\bverilog\b", r"\bvhdl\b"),
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
    "Embedded Software Engineer": ("Embedded Systems", "C", "C++", "Microcontrollers", "RTOS", "Git"),
    "Firmware Engineer": ("Firmware", "C", "C++", "Microcontrollers", "STM32", "ESP32", "UART", "SPI", "I2C"),
    "Embedded Linux Engineer": ("Embedded Linux", "Linux", "C", "C++", "Device Drivers"),
    "RTOS / Device Driver Engineer": ("RTOS", "C", "C++", "Device Drivers", "UART", "SPI", "I2C"),
    "IoT Firmware Engineer": ("Firmware", "ESP32", "Arduino", "Microcontrollers", "C++", "Embedded Systems"),
    "UI/UX Designer": ("Figma", "UX Research", "Wireframing"),
    "Digital Marketing Specialist": ("SEO", "Social Media Marketing", "Google Analytics"),
}



# Career field is kept separate from shared tools such as Git, Python and Linux.
# A beginner can correct auto-detection on the website before searching.
CAREER_DOMAINS = (
    "Embedded Systems / Firmware", "Data & Analytics", "Software / Web Development",
    "DevOps / Cloud", "Electronics / Hardware", "Design / UX",
    "Digital Marketing", "General / Not sure",
)

ROLE_DOMAIN = {
    "Junior Data Analyst": "Data & Analytics",
    "Junior Data Scientist": "Data & Analytics",
    "Business Analyst": "Data & Analytics",
    "Python Developer": "Software / Web Development",
    "Frontend Developer": "Software / Web Development",
    "Backend Developer": "Software / Web Development",
    "DevOps / Cloud Engineer": "DevOps / Cloud",
    "UI/UX Designer": "Design / UX",
    "Digital Marketing Specialist": "Digital Marketing",
    "Embedded Software Engineer": "Embedded Systems / Firmware",
    "Firmware Engineer": "Embedded Systems / Firmware",
    "Embedded Linux Engineer": "Embedded Systems / Firmware",
    "RTOS / Device Driver Engineer": "Embedded Systems / Firmware",
    "IoT Firmware Engineer": "Embedded Systems / Firmware",
}

# Deliberately require *specialized* evidence. Git/Linux/Python alone cannot
# classify a resume as DevOps, and general mention of "embedded dashboards"
# cannot classify a resume as embedded engineering.
DOMAIN_EVIDENCE = {
    "Embedded Systems / Firmware": (
        r"\bembedded\s+(?:systems?|software|linux|programming|development|engineer)\b",
        r"\bfirmware\b", r"\brtos\b", r"\bfree\s?rtos\b",
        r"\bmicrocontrollers?\b", r"\bstm32[a-z0-9]*\b",
        r"\besp32\b", r"\bdevice\s+drivers?\b", r"\bbare[ -]?metal\b",
        r"\buart\b", r"\bi2c\b", r"\bspi\b", r"\bcan\s+bus\b",
    ),
    "DevOps / Cloud": (r"\bdevops\b", r"\bkubernetes\b", r"\bk8s\b", r"\bterraform\b", r"\bci/cd\b", r"\bsite reliability\b"),
    "Data & Analytics": (r"\bdata (?:analyst|scientist|analysis|analytics)\b", r"\bpower\s*bi\b", r"\btableau\b", r"\bpandas\b", r"\bmachine learning\b"),
    "Software / Web Development": (r"\b(?:frontend|backend|full[ -]?stack|web)\s+(?:developer|engineer|development)\b", r"\breact(?:\.js|js)?\b", r"\bdjango\b", r"\bjavascript\b"),
    "Electronics / Hardware": (r"\bpcb(?:\s+(?:design|layout))?\b", r"\bfpga\b", r"\bvhdl\b", r"\bverilog\b", r"\bcircuit\s+design\b"),
    "Design / UX": (r"\bux research\b", r"\bui/ux\b", r"\bwireframes?\b", r"\bfigma\b"),
    "Digital Marketing": (r"\bsearch engine optimization\b", r"\bseo\b", r"\bsocial media marketing\b", r"\bgoogle analytics\b"),
}


def infer_career_domain(resume_text: str) -> str:
    """Conservative field guess from specialized evidence, not a qualification check."""
    scores = {domain: sum(bool(re.search(pattern, resume_text, re.I)) for pattern in patterns)
              for domain, patterns in DOMAIN_EVIDENCE.items()}
    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # Require at least two independent signals, avoiding single-keyword errors.
    if not ranking or ranking[0][1] < 2:
        return "General / Not sure"
    # Avoid guessing when two domains have identical, nontrivial evidence.
    if len(ranking) > 1 and ranking[0][1] == ranking[1][1]:
        return "General / Not sure"
    return ranking[0][0]

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


def suggest_roles(skills: list[str], limit: int = 5, primary_domain: str = "General / Not sure") -> list[RoleSuggestion]:
    have = set(skills)
    results: list[RoleSuggestion] = []
    for role, desired in ROLE_SKILLS.items():
        if primary_domain != "General / Not sure" and ROLE_DOMAIN.get(role) != primary_domain:
            continue
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

"""Resume-section extraction and evidence features; not a fixed list of occupations.

RoleRoute uses job titles, work history, projects, summary, education and skills.
All statements are evidence observed in text, not independent credential verification.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

SECTION_RE = re.compile(
    r'^(?P<header>(?:professional\s+|career\s+|executive\s+)?summary|profile|about\s+me|'
    r'career\s+objective|objective|(?:professional\s+|work\s+|employment\s+|relevant\s+)?experience|'
    r'work\s+history|internships?|employment|(?:academic\s+|personal\s+|technical\s+|key\s+)?projects?|'
    r'education|academic\s+(?:background|qualifications?)|qualifications?|'
    r'(?:technical\s+|core\s+)?skills?|technical\s+stack|technologies|'
    r'certifications?|licenses?|achievements?|awards?)\s*(?::\s*(?P<value>.*))?$', re.I)
TITLE_LABEL = re.compile(r'^(?:current|previous|professional|target|desired|job|career)\s*'
                         r'(?:title|role|position|designation)\s*[:\-]\s*(.{3,110})$', re.I)
# Occupational suffixes are grammatical signals, not a catalog of predefined jobs.
OCCUPATION = re.compile(r'\b(?:engineer|developer|analyst|scientist|architect|designer|'
                        r'consultant|specialist|technician|manager|administrator|researcher|'
                        r'accountant|recruiter|writer|auditor|executive|programmer|tester)\b', re.I)
EXCLUDE_LINE = re.compile(r'@|https?://|\+?\d[\d\s.-]{9,}\d', re.I)
STOP = set('and of the for in on with to a an as at by professional experienced skilled motivated seeking looking career objective profile resume summary education'.split())

# Technical concept equivalences: *not* job-title mappings or a limited career catalog.
# They allow 'firmware' and 'microcontroller' to share a concept without confusing
# general-purpose tools like Git/Linux with career evidence.
TOPICS = {
    'embedded': (r'\bembedded\b', r'\bfirmware\b', r'\bmicrocontroller\b', r'\bstm32\b',
                 r'\besp32\b', r'\brtos\b', r'\bfreertos\b', r'\bdevice\s+driver\b',
                 r'\buart\b', r'\bi2c\b', r'\bspi\b', r'\bbare[ -]?metal\b'),
    'devops': (r'\bdevops\b', r'\bsre\b', r'\bsite\s+reliability\b', r'\bkubernetes\b',
               r'\bterraform\b', r'\bci\s*/\s*cd\b', r'\binfrastructure\s+as\s+code\b'),
    'analytics': (r'\banalyst\b', r'\banalytics?\b', r'\bdata\s+scien\w*\b',
                  r'\bpower\s*bi\b', r'\btableau\b', r'\bdashboards?\b', r'\bbusiness\s+intelligence\b'),
    'web': (r'\bfront[ -]?end\b', r'\bback[ -]?end\b', r'\bfull[ -]?stack\b',
            r'\breact\b', r'\bangular\b', r'\bweb\s+(?:app|application|developer)\b',
            r'\bdjango\b', r'\bspring\s+boot\b'),
    'hardware': (r'\bpcb\b', r'\bcircuit\s+design\b', r'\bf?pgas?\b',
                 r'\bverilog\b', r'\bvhdl\b', r'\bvlsi\b'),
    'finance': (r'\bfinance\b', r'\bfinancial\b', r'\baccounting\b', r'\baudit\b', r'\btaxation\b'),
    'marketing': (r'\bmarketing\b', r'\bseo\b', r'\bbrand\s+strategy\b', r'\badvertising\b'),
}


@dataclass(frozen=True)
class ResumeProfile:
    titles: tuple[str, ...]
    summary: str
    work_experience: str
    projects: str
    education: str
    skills_section: str
    certifications: str
    other: str

    @property
    def full_career_evidence(self) -> str:
        return ' '.join((*(self.titles), self.summary, self.work_experience, self.projects)).strip()


def _occupational_title(text: str) -> str | None:
    text = re.sub(r'^\s*[•\-]+\s*', '', text.strip())
    text = re.split(r'\s*[|•]\s*|\s+[—–]\s+|\s+-\s+(?=[A-Z])|\s+at\s+', text)[0].strip()
    if not text or len(text) > 90 or EXCLUDE_LINE.search(text):
        return None
    # A short standalone 'Embedded Systems Engineer' is credible title evidence.
    if len(text.split()) <= 9 and OCCUPATION.search(text) and not re.search(r'[.!?;]', text):
        return text
    # In a summary, 'Embedded Engineer with 3 years...' is career title evidence.
    match = re.match(r'^\s*(.{4,70}?\b(?:engineer|developer|analyst|scientist|architect|designer|'
                     r'consultant|specialist|technician|manager|administrator|researcher|'
                     r'accountant|recruiter|writer|auditor|executive|programmer|tester))\b'
                     r'(?=\s+(?:with|having|who|experienced|focused|specializing|\d)|\s*[,:.]|$)', text, re.I)
    if match and len(match.group(1).split()) <= 8:
        return match.group(1).strip()
    return None


def parse_resume(text: str) -> ResumeProfile:
    lines = [line.strip() for line in text.splitlines()]
    buckets: dict[str, list[str]] = {k: [] for k in ('preamble', 'summary', 'work', 'projects', 'education', 'skills', 'certifications', 'other')}
    current = 'preamble'
    title_hints: list[str] = []
    for index, line in enumerate(lines):
        if not line:
            continue
        named_title = TITLE_LABEL.match(line)
        if named_title:
            maybe = _occupational_title(named_title.group(1))
            if maybe:
                title_hints.append(maybe)
            continue
        heading = SECTION_RE.match(line)
        if heading:
            word = heading.group('header').lower()
            if 'project' in word:
                current = 'projects'
            elif any(x in word for x in ('experience', 'employment', 'internship', 'work history')):
                current = 'work'
            elif any(x in word for x in ('summary', 'profile', 'objective', 'about me')):
                current = 'summary'
            elif any(x in word for x in ('education', 'academic', 'qualification')):
                current = 'education'
            elif any(x in word for x in ('skill', 'technical stack', 'technologies')):
                current = 'skills'
            elif any(x in word for x in ('certification', 'license')):
                current = 'certifications'
            else:
                current = 'other'
            if heading.group('value'):
                buckets[current].append(heading.group('value')[:250])
            continue
        buckets[current].append(line[:450])
    # Header, summary and work experience are plausible locations for a stated
    # current or desired title; do not mistake project titles for paid positions.
    candidate_lines = buckets['preamble'][:10] + buckets['summary'][:4] + buckets['work'][:12]
    for line in candidate_lines:
        maybe = _occupational_title(line)
        if maybe and maybe.casefold() not in {v.casefold() for v in title_hints}:
            title_hints.append(maybe)
    def join(key: str) -> str:
        return '\n'.join(buckets[key])[:12000]
    return ResumeProfile(
        titles=tuple(title_hints[:6]), summary=join('summary'),
        work_experience=join('work'), projects=join('projects'),
        education=join('education'), skills_section=join('skills'),
        certifications=join('certifications'),
        other='\n'.join(buckets['preamble'][:12] + buckets['other'][:10])[:3000],
    )


def meaningful_terms(text: str) -> set[str]:
    values = set()
    for term in re.findall(r'[a-z][a-z0-9+#.]*', text.casefold()):
        if len(term) < 3 or term in STOP or term in {'engineer', 'developer', 'specialist', 'intern', 'junior', 'senior', 'manager'}:
            continue
        if term in {'analytics', 'analyst', 'analysis', 'analytical'}:
            term = 'analytics'
        if term in {'firmwares'}:
            term = 'firmware'
        values.add(term)
    return values


def topic_weights(profile: ResumeProfile) -> dict[str, float]:
    """Prioritize declared title and demonstrated career work over tool name matches."""
    weights = {topic: 0.0 for topic in TOPICS}
    for content, factor in [('\n'.join(profile.titles), 5.0), (profile.work_experience, 2.5),
                            (profile.projects, 2.0), (profile.summary, 1.6),
                            (profile.education, 0.5), (profile.skills_section, 0.30)]:
        for topic, patterns in TOPICS.items():
            n = sum(bool(re.search(pattern, content, re.I)) for pattern in patterns)
            weights[topic] += factor * min(3, n)
    return weights


def dominant_topic(profile: ResumeProfile) -> tuple[str | None, float]:
    scores = sorted(topic_weights(profile).items(), key=lambda x: -x[1])
    if not scores or scores[0][1] < 1.8:
        return None, 0.0
    if len(scores) > 1 and scores[1][1] >= .9 * scores[0][1]:
        return None, scores[0][1]
    return scores[0]


def job_topics(title: str, description: str) -> tuple[set[str], set[str]]:
    title_topics = {topic for topic, patterns in TOPICS.items()
                    if any(re.search(p, title, re.I) for p in patterns)}
    desc_topics = {topic for topic, patterns in TOPICS.items()
                   if sum(bool(re.search(p, description[:10000], re.I)) for p in patterns) >= 2}
    return title_topics, desc_topics


def overlap_ratio(first: str, second: str) -> float:
    t1 = meaningful_terms(first)
    t2 = meaningful_terms(second)
    return len(t1 & t2) / max(1, min(6, len(t1), len(t2)))

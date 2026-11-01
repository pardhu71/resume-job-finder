"""RoleRoute v5: resume-to-actual-job-description matching, NO fixed job role list.

Heuristics are deliberately conservative. No score means probability of hiring;
no classifier claims confirmed eligibility. Text supplied by job boards is untrusted.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections import Counter

from analyzer import find_skills
from job_sources import JobListing, chosen_scope, location_text_matches, location_is_india, canonical_job_key, remote_eligibility

STOP = set('the and or with for from your their our you work in on at as to of by use using knowledge have ability strong good understanding experience years year minimum required preferred must plus team systems engineering engineer developer specialist internship intern candidate position role skills skill technologies technology projects project build built based develop developed development designing design various include including working worked experience professional implementation'.split())
GENERIC = set('python sql git github linux excel communication management microsoft office teamwork testing programming software api cloud data business partner c c++ java'.split())
PREFERRED = re.compile(r'\b(?:preferred|nice to have|bonus|plus if|desirable|ideally|good to have)\b', re.I)
MANDATORY = re.compile(r'\b(?:required|must have|mandatory|minimum qualification|essential skills?|you must|requirement[s]?:)\b', re.I)
YEAR = re.compile(r'(?<!\d)(\d{1,2})\s*(?:\+|to\s*\d{1,2}|[-–]\s*\d{1,2})?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+|professional\s+|hands.on\s+|work\s+){0,3}experience\b', re.I)
SENIOR = re.compile(r'\b(?:senior|staff|principal|director|vp|vice president|head of|lead engineer|engineering manager)\b', re.I)
DEGREE = re.compile(r'\b(?:bachelor.s degree|master.s degree|b\.?tech|b\.?e\.?|b\.?sc|m\.?tech|phd|doctorate|mba)\b', re.I)
PHONE = re.compile(r'(?<!\w)(?:\+?\d[\d\s().-]{8,}\d)(?!\w)')
EMAIL = re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b')
LINK = re.compile(r'https?://\S+', re.I)


def clean_tokens(value: str) -> list[str]:
    # Light word normalization handles "analysis" vs "analyst" without
    # hardcoding any list of job titles or career paths.
    terms = []
    for v in re.findall(r'[a-z][a-z0-9+#.-]*', value.lower()):
        if len(v) <= 2 or v in STOP:
            continue
        if v in ('analysis', 'analytics', 'analyst', 'analytical', 'analyzing', 'analyze'):
            v = 'analys'
        elif v in ('scientist', 'science'):
            v = 'scien'
        elif v in ('developer', 'developing', 'development'):
            v = 'develop'
        terms.append(v)
    return terms


def extract_resume_skills(resume: str) -> tuple[str, ...]:
    """Find known technical terms AND additional comma-delimited resume skill labels."""
    skills = set(find_skills(resume))
    resume_lines = resume.splitlines()
    # Accept common multi-line resume skill sections without a prebuilt role catalog.
    in_skill_section = False
    for raw in resume_lines:
        section_match = re.match(r'^\s*(?:technical\s+)?(?:skills?|technologies|technical stack|tools?\s*(?:&|and)\s*technologies)\s*:?\s*(.*)$', raw, re.I)
        if section_match:
            in_skill_section = True
            content = section_match.group(1)[:400]
        elif in_skill_section:
            if re.match(r'^\s*(?:education|projects?|work experience|experience|internships?|summary|certifications?|achievements?|interests?|contact|objective|languages?)\s*:?\s*$', raw, re.I):
                in_skill_section = False
                continue
            # Avoid treating entire paragraphs and contact details as skills.
            if not raw.strip() or len(raw) > 150 or '@' in raw:
                in_skill_section = False
                continue
            content = raw.strip().lstrip('•- ')[:400]
        else:
            continue
        for piece in re.split(r',|\||;|\u2022', content):
            value = piece.strip(' .\t-')
            if 2 <= len(value) <= 38 and len(value.split()) <= 4 and not re.search(r'[@\d]{5,}', value):
                skills.add(value)
    return tuple(sorted(skills, key=str.casefold))


def resume_focus(resume: str, extra: str = '') -> str:
    """Derive interests/target roles/projects from resume text, rather than predefined roles."""
    chosen = []
    if extra.strip():
        chosen.append(extra.strip()[:180])
    for raw in resume.splitlines():
        line = raw.strip()
        if re.search(r'\b(?:interested in|seeking|target role[s]?|career goal|objective|specialization|focus(?:ed)? on)\b', line, re.I):
            chosen.append(line[:230])
        elif re.match(r'^(?:projects?|work experience|internships?|summary)\s*:', line, re.I):
            chosen.append(line[:230])
    # Use full text as backstop for resumes with no structured project lines.
    if not chosen:
        chosen = [resume[:500]]
    return ' '.join(chosen)[:1100]


def focus_search_query(focus: str) -> str:
    """Derive short public-search keywords from a resume interest, no role catalog."""
    match = re.search(r'\b(?:interested in|seeking|target roles?[:\s]+|career goal[:\s]+)\s*(.{3,120})', focus, re.I)
    if match:
        return re.sub(r'[^\w\s+#./-]', ' ', match.group(1)).strip()[:75]
    tokens = list(dict.fromkeys(clean_tokens(focus)))
    return ' '.join(tokens[:6])[:75] or 'entry level jobs'


def safe_llm_profile(resume: str, extra: str = '') -> dict:
    """Send only skill tags and redacted project/interest signals, never the whole resume."""
    focus = resume_focus(resume, extra)
    focus = EMAIL.sub('[email removed]', focus)
    focus = PHONE.sub('[phone removed]', focus)
    focus = LINK.sub('[link removed]', focus)
    safe_skills = []
    for skill in extract_resume_skills(resume):
        skill = LINK.sub('[link removed]', PHONE.sub('[phone removed]', EMAIL.sub('[email removed]', skill)))
        if '[' not in skill:
            safe_skills.append(skill)
    return {'skills': safe_skills[:65], 'career_focus': focus[:850]}


def skill_in_text(skill: str, text: str) -> bool:
    if not text or not skill.strip():
        return False
    # exact bounded phrase; protects against matching C to 'science'.
    return bool(re.search(r'(?<![\w])' + re.escape(skill.lower()) + r'(?![\w])', text.lower()))


def extract_job_requirement_terms(description: str) -> tuple[str, ...]:
    """Catch employer-listed required/preferred terms not in our starter skill lexicon.

    Restricted to explicit comma/bullet skill lists; not a full semantic parser.
    Avoid treating education/years/whole sentences as technical skills.
    """
    found = []
    for fragment in re.split(r'[\n;]|(?<=[.!?])\s+', description[:24000]):
        match = re.match(r'^\s*(?:required(?:\s+skills?)?|requirements?|must\s+have|preferred(?:\s+skills?)?|nice\s+to\s+have)\s*:\s*(.{2,240})', fragment, re.I)
        if not match:
            continue
        items = re.split(r',|\s+and\s+|\s+&\s+|[\u2022|]', match.group(1))
        for item in items:
            value = item.strip(' .-:()\t')
            value = re.sub(r'^(?:strong\s+|hands.on\s+|knowledge\s+of\s+|experience\s+(?:in|with)\s+)', '', value, flags=re.I)
            if not (2 <= len(value) <= 42 and len(value.split()) <= 4):
                continue
            if re.search(r'\b(?:years?|yrs?|degree|graduate|visa|salary|benefits|apply|experience)\b', value, re.I):
                continue
            if value.lower() not in {x.lower() for x in found}:
                found.append(value)
    return tuple(found[:50])


def requirement_signals(description: str, skills: tuple[str, ...], extra_skills: tuple[str, ...] = ()) -> dict[str, tuple[str, ...]]:
    """Classify skills as required/preferred/mentioned only when there is textual evidence.

    Most flattened feeds lose bullet hierarchy; ambiguous matches remain 'mentioned'.
    """
    catalog = tuple(dict.fromkeys([*skills, *extra_skills]))
    seen: dict[str, str] = {}
    # Allow simple text/newlines/sentences; job-board HTML is flattened upstream.
    sections = re.split(r'(?<=[.;\n])\s+|\s*[•\u2022]\s*', description[:24000])
    for section in sections:
        if not section:
            continue
        matches = [skill for skill in catalog if skill_in_text(skill, section)]
        if not matches:
            continue
        category = 'preferred' if PREFERRED.search(section) else 'required' if MANDATORY.search(section) else 'mentioned'
        for skill in matches:
            if skill not in seen or (category == 'required' and seen[skill] != 'required') or (category == 'preferred' and seen[skill] == 'mentioned'):
                seen[skill] = category
    return {group: tuple(sorted((x for x, g in seen.items() if g == group), key=str.casefold)) for group in ('required','preferred','mentioned')}


def years_requirement(text: str) -> tuple[int | None, str]:
    """Return only clearly mandatory minimums; preferred years aren't a hard conflict."""
    required = []
    preferred = []
    for sentence in re.split(r'[.\n;]|\u2022', text[:20000]):
        for match in YEAR.finditer(sentence):
            years = int(match.group(1))
            if PREFERRED.search(sentence):
                preferred.append(years)
            else:
                required.append(years)
    if required:
        return max(required), 'minimum years mentioned (review original wording)'
    if preferred:
        return None, f'{max(preferred)}+ years preferred, not treated as mandatory'
    return None, 'minimum years not confidently found'


def focus_alignment(job: JobListing, focus: str, skills: tuple[str, ...]) -> tuple[float, tuple[str, ...], bool]:
    """Check title/subject alignment separately from generic shared tools.

    Focus terms come from user's resume; does not map to predefined careers.
    """
    focus_tokens = set(clean_tokens(focus))
    job_title = set(clean_tokens(job.title))
    # Do not let generic 'engineer', 'software' etc outweigh specialized focus.
    related = sorted(focus_tokens & job_title)
    special_in_title = [w for w in related if w not in GENERIC]
    specific_skills = [s for s in skills if s.lower() not in GENERIC and len(s) >= 3 and skill_in_text(s, job.description)]
    title_ratio = len(special_in_title) / max(1, min(4, len(job_title)))
    # job descriptions can mention incidental tools; title boost is intentionally larger
    alignment = min(1., .75 * title_ratio + .09 * min(3, len(specific_skills)))
    aligned = bool(special_in_title) or len(specific_skills) >= 2
    return alignment, tuple(special_in_title), aligned


@dataclass(frozen=True)
class DetailedMatch:
    job: JobListing
    score: int
    category: str                 # Strong | Possible | Review / conflict
    found_required: tuple[str, ...]
    missing_required: tuple[str, ...]
    found_preferred: tuple[str, ...]
    missing_preferred: tuple[str, ...]
    found_mentioned: tuple[str, ...]
    role_evidence: tuple[str, ...]
    experience_note: str
    location_note: str
    warnings: tuple[str, ...]
    description_available: bool


def evaluate_job(job: JobListing, resume: str, focus: str, years: int | None, country: str='India',
                 have_skills: tuple[str, ...] | None = None) -> DetailedMatch:
    have = have_skills if have_skills is not None else extract_resume_skills(resume)
    catalog = set(have) | set(find_skills(job.description + ' ' + job.title)) | set(extract_job_requirement_terms(job.description))
    # For user-provided skills not in the known dictionary, exact phrase matching works.
    signals = requirement_signals(job.description, tuple(catalog))
    def present(xs: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(s for s in xs if any(s.casefold() == h.casefold() for h in have))
    def not_present(xs: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(s for s in xs if not any(s.casefold() == h.casefold() for h in have))
    required = signals['required']
    preferred = signals['preferred']
    mentioned = signals['mentioned']
    found_req = present(required)
    miss_req = not_present(required)
    found_pref = present(preferred)
    miss_pref = not_present(preferred)
    found_other = present(mentioned)
    align, role_evidence, domain_ok = focus_alignment(job, focus, have)
    years_min, years_note = years_requirement(job.description)
    if years_min is not None:
        years_note = (f'Listing mentions {years_min}+ years; profile states {years}'
                      if years is not None else f'Listing mentions {years_min}+ years; applicant experience not confirmed')
    caution = []
    conflict = False
    if years_min is not None and years is None:
        caution.append('Years of experience need confirmation')
    elif years_min is not None and years_min > years:
        caution.append('Possible minimum-experience conflict; verify if mandatory')
        conflict = True
    elif SENIOR.search(job.title) and years is None:
        caution.append('Senior-level role: applicant years of experience need confirmation')
    elif SENIOR.search(job.title) and years is not None and years < 2:
        caution.append('Senior-level title may not suit an entry-level applicant')
        conflict = True
    if job.is_remote:
        geo = remote_eligibility(job)
        locnote = f'Remote: {geo}'
        if country.strip().casefold() == 'india' and geo.startswith('Geographically restricted'):
            caution.append('Remote location may exclude applicants based in India')
            conflict = True
    else:
        locnote = f'Listed location: {job.location}; work authorization not verified'
        if country.strip().casefold() == 'india' and not location_is_india(job.location):
            caution.append('International role; visa or work authorization not checked')
    if not job.description.strip():
        caution.append('Full description unavailable; requirements cannot be verified')
    if not domain_ok:
        caution.append('No convincing career-focus match in the title or specialized requirements')
    if miss_req:
        caution.append('Some skills mentioned as required are not evidenced in the resume')
    # 'Unknown' is not a confirmed mismatch. Do not score empty descriptions highly.
    req_score = len(found_req)/len(required) if required else .40
    pref_score = len(found_pref)/len(preferred) if preferred else .40
    detail_score = min(1., len(found_other) / 3)
    exp_score = 1. if years_min is not None and years is not None and years >= years_min else .5 if (years_min is None or years is None) else 0.
    score = round(40 * req_score + 10 * pref_score + 15 * detail_score + 30 * align + 5 * exp_score)
    if not job.description.strip():
        score = min(score, 35)
    if not domain_ok:
        score = min(score, 42)
    if conflict:
        score = min(score, 35)
    if miss_req:
        score = min(score, 60)
    if conflict or (not job.description.strip()) or (not domain_ok):
        category = 'Review / conflict'
    elif align >= .25 and (not required or req_score >= .65) and not miss_req and score >= 60 and not (years is None and (years_min is not None or SENIOR.search(job.title))):
        category = 'Strong'
    else:
        category = 'Possible'
    return DetailedMatch(
        job=job, score=max(0, min(100, score)), category=category,
        found_required=found_req, missing_required=miss_req,
        found_preferred=found_pref, missing_preferred=miss_pref,
        found_mentioned=found_other, role_evidence=role_evidence,
        experience_note=years_note, location_note=locnote,
        warnings=tuple(caution), description_available=bool(job.description.strip()),
    )


def rank_jobs(jobs: list[JobListing], resume: str, focus: str, years: int | None,
              scopes: set[str], country: str = 'India', city: str = '', max_results: int = 40) -> tuple[list[DetailedMatch], dict]:
    # Do not use a predefined role catalog. Evaluate real descriptions, and
    # keep uncertain and rejected listings distinct for exploration.
    seen: set[str] = set()
    candidate_skills = extract_resume_skills(resume)  # compute once, not once per retrieved vacancy
    included: list[DetailedMatch] = []
    stats = Counter(retrieved=len(jobs))
    for job in jobs:
        key = canonical_job_key(job)
        if key in seen:
            continue
        seen.add(key)
        stats['unique'] += 1
        if not chosen_scope(job, scopes):
            stats['region_removed'] += 1
            continue
        stats['in_region'] += 1
        # Non-strict city: city is a preference, not a hard exclusion.
        item = evaluate_job(job, resume, focus, years, country, have_skills=candidate_skills)
        if 'No convincing career-focus match' in ' '.join(item.warnings):
            stats['unrelated_removed'] += 1
            continue
        if city and location_text_matches(job.location, city):
            item = DetailedMatch(**{**vars(item), 'score': min(100, item.score + 3)})
        included.append(item)
        stats[item.category] += 1
    priority = {'Strong':0, 'Possible':1, 'Review / conflict':2}
    included.sort(key=lambda x: (priority[x.category], -x.score, x.job.title.casefold()))
    # Keep some weaker leads discoverable, rather than claim there are no jobs.
    return included[:max_results], dict(stats)

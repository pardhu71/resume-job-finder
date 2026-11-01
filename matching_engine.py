"""RoleRoute v5: resume-to-actual-job-description matching, NO fixed job role list.

Heuristics are deliberately conservative. No score means probability of hiring;
no classifier claims confirmed eligibility. Text supplied by job boards is untrusted.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections import Counter

from analyzer import find_skills
from resume_profile import parse_resume, dominant_topic, job_topics, overlap_ratio, meaningful_terms, ResumeProfile
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
    """Build search focus from the whole resume, including *stated career titles*.

    No predefined occupation list determines candidate roles. The resume is
    read for titles, summary, work, projects, education, and specialized skills.
    """
    profile = parse_resume(resume)
    pieces = [extra.strip()[:180]] if extra.strip() else []
    pieces.extend(profile.titles)
    pieces.extend((profile.summary[:360], profile.work_experience[:360],
                   profile.projects[:440], profile.education[:170],
                   profile.skills_section[:220]))
    return ' '.join(x for x in pieces if x)[:1700] or resume[:600]


def focus_search_query(focus: str) -> str:
    """Derive short public-search keywords from a resume interest, no role catalog."""
    match = re.search(r'\b(?:interested in|seeking|target roles?[:\s]+|career goal[:\s]+)\s*(.{3,120})', focus, re.I)
    if match:
        return re.sub(r'[^\w\s+#./-]', ' ', match.group(1)).strip()[:75]
    tokens = list(dict.fromkeys(clean_tokens(focus)))
    return ' '.join(tokens[:6])[:75] or 'entry level jobs'


def safe_llm_profile(resume: str, extra: str = '') -> dict:
    """Send only skill tags and redacted project/interest signals, never the whole resume."""
    profile = parse_resume(resume)
    def redact(value: str, limit: int) -> str:
        # Contact details are removed before opt-in LLM calls; use the preview
        # control to inspect any remaining sensitive employers/projects.
        value = EMAIL.sub('[email removed]', value)
        value = PHONE.sub('[phone removed]', value)
        value = LINK.sub('[link removed]', value)
        return value[:limit]
    focus = redact(resume_focus(resume, extra), 850)
    safe_skills = []
    for skill in extract_resume_skills(resume):
        skill = LINK.sub('[link removed]', PHONE.sub('[phone removed]', EMAIL.sub('[email removed]', skill)))
        if '[' not in skill:
            safe_skills.append(skill)
    return {'skills': safe_skills[:65], 'career_focus': focus,
            'stated_titles': [redact(title, 90) for title in profile.titles[:5]],
            'summary_excerpt': redact(profile.summary, 250),
            'work_excerpt': redact(profile.work_experience, 300),
            'projects_excerpt': redact(profile.projects, 360),
            'education_excerpt': redact(profile.education, 180)}


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


def whole_resume_alignment(job: JobListing, profile: ResumeProfile,
                           focus: str) -> tuple[float, tuple[str, ...], bool, tuple[str, ...]]:
    """Compare job's career intent to candidate titles, work, projects, summary.

    Shared generic programming tools cannot by themselves establish career fit.
    The topic vocabulary is a loose technical synonym aid, not a job catalog.
    """
    job_title_topics, job_description_topics = job_topics(job.title, job.description)
    primary_topic, topic_confidence = dominant_topic(profile)
    direct_title = max((overlap_ratio(t, job.title) for t in profile.titles), default=0.0)
    same_title_topic = bool(primary_topic and primary_topic in job_title_topics)
    same_description_topic = bool(primary_topic and primary_topic in job_description_topics)
    # A very different specialized job title is evidence of a domain mismatch,
    # even when the listing happens to mention Python, Excel, Git, or Linux.
    different_career = bool(primary_topic and topic_confidence >= 2.5 and (
        (job_title_topics and primary_topic not in job_title_topics) or
        (not job_title_topics and len(job_description_topics) == 1
         and primary_topic not in job_description_topics)))
    if same_title_topic:
        title_score = max(direct_title, .95)
    elif direct_title:
        title_score = direct_title
    elif same_description_topic:
        title_score = .56
    elif not profile.titles and primary_topic and (same_description_topic or same_title_topic):
        title_score = .50
    else:
        title_score = 0.0
    project_overlap = overlap_ratio(profile.projects, job.title + ' ' + job.description[:2800])
    work_overlap = overlap_ratio(profile.work_experience, job.title + ' ' + job.description[:2800])
    summary_overlap = overlap_ratio(profile.summary, job.title + ' ' + job.description[:1800])
    project_score = max(project_overlap, .90 if same_title_topic and profile.projects else
                        .70 if same_description_topic and profile.projects else 0.0)
    work_score = max(work_overlap, .80 if same_title_topic and profile.work_experience else 0.0)
    summary_score = max(summary_overlap, .55 if same_title_topic and profile.summary else 0.0)

    # Full-resume subject match. If there is no explicit career title, projects
    # and experience may still establish the professional direction.
    field_score = max(title_score,
                      .83 if not profile.titles and same_title_topic and profile.projects else 0.0,
                      .62 if not profile.titles and same_description_topic and profile.projects else 0.0,
                      .64 if not profile.titles and same_title_topic and profile.work_experience else 0.0)
    if different_career:
        field_score = min(field_score, .10)
    project_specific = len(meaningful_terms(profile.projects) &
                           meaningful_terms(job.title + ' ' + job.description[:2800])) >= 2
    work_specific = len(meaningful_terms(profile.work_experience) &
                        meaningful_terms(job.title + ' ' + job.description[:2800])) >= 2
    career_ok = not different_career and (
        field_score >= .32 or (project_specific and project_score >= .25)
        or (work_specific and work_score >= .25)
        or (summary_score >= .40 and bool(job_title_topics | job_description_topics)))
    alignment = min(1.0, .66 * field_score + .16 * project_score +
                    .12 * work_score + .06 * summary_score)

    evidence = []
    if field_score >= .32:
        if profile.titles:
            evidence.append('Career title: ' + ', '.join(profile.titles[:2]))
        elif primary_topic:
            evidence.append('Career direction indicated by resume: ' + primary_topic)
    if project_score >= .20 and profile.projects:
        evidence.append('Technical projects support this role')
    if work_score >= .20 and profile.work_experience:
        evidence.append('Work or internship experience supports this role')
    if summary_score >= .20 and profile.summary:
        evidence.append('Professional summary supports this role')
    if not evidence and primary_topic:
        evidence.append('Career focus needs verification: ' + primary_topic)
    details = []
    if profile.titles:
        details.append('Career title(s) examined: ' + ', '.join(profile.titles[:3]))
    if profile.summary:
        details.append('Professional summary compared')
    if profile.work_experience:
        details.append('Work/internship history compared')
    if profile.projects:
        details.append('Projects compared with job responsibilities')
    if profile.education:
        details.append('Education compared')
    return alignment, tuple(evidence), career_ok, tuple(details)


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
    evidence_details: tuple[str, ...] = ()


def evaluate_job(job: JobListing, resume: str, focus: str, years: int | None, country: str='India',
                 have_skills: tuple[str, ...] | None = None,
                 profile: ResumeProfile | None = None) -> DetailedMatch:
    have = have_skills if have_skills is not None else extract_resume_skills(resume)
    profile = profile if profile is not None else parse_resume(resume)
    catalog = set(have) | set(find_skills(job.description + ' ' + job.title)) | set(extract_job_requirement_terms(job.description))
    # For user-provided skills not in the known dictionary, exact phrase matching works.
    signals = requirement_signals(job.description, tuple(catalog))
    def present(xs: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(s for s in xs if any(s.casefold() == h.casefold() for h in have) or skill_in_text(s, resume))
    def not_present(xs: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(s for s in xs if not (any(s.casefold() == h.casefold() for h in have) or skill_in_text(s, resume)))
    required = signals['required']
    preferred = signals['preferred']
    mentioned = signals['mentioned']
    found_req = present(required)
    miss_req = not_present(required)
    found_pref = present(preferred)
    miss_pref = not_present(preferred)
    found_other = present(mentioned)
    align, role_evidence, domain_ok, evidence_details = whole_resume_alignment(job, profile, focus)
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
    # Career and project evidence outweigh incidental tool overlap. Not a
    # probability of hiring, and incomplete descriptions must remain uncertain.
    req_score = len(found_req) / len(required) if required else .50
    pref_score = len(found_pref) / len(preferred) if preferred else .50
    skills_score = min(1.0, (len(found_req) + .35 * len(found_pref) +
                             .15 * len(found_other)) / max(1.0, len(required) + .35 * len(preferred)))
    years_score = (1.0 if years_min is not None and years is not None and years >= years_min
                   else .50 if years_min is None or years is None else 0.0)
    # Compare stated qualifications when the job includes an explicit degree.
    education_text = profile.education + ' ' + resume[:800]
    job_degree = re.findall(r'\b(?:ph\.?d|doctorate|master(?:s)?|bachelor(?:s)?|b\.?tech|m\.?tech|mba|b\.?sc|m\.?sc)\b', job.description, re.I)
    # We cannot verify equivalence of all international degree names, so this
    # score only means the resume visibly mentions the stated level.
    edu_evidenced = (not job_degree or any(re.search(r'\b' + re.escape(degree) + r'\b', education_text, re.I)
                                         for degree in job_degree))
    edu_score = .50 if not job_degree else 1.0 if edu_evidenced else 0.0
    if job_degree and not edu_evidenced:
        caution.append('Degree mentioned in job but not evidenced in resume; check exact qualification')
    score = round(58 * align + 25 * skills_score + 8 * req_score +
                  3 * pref_score + 4 * years_score + 2 * edu_score)
    if not job.description.strip():
        score = min(score, 35)
    if not domain_ok:
        score = min(score, 35)
    if conflict:
        score = min(score, 35)
    if miss_req:
        score = min(score, 62)
    if conflict or not job.description.strip() or not domain_ok:
        category = 'Review / conflict'
    elif align >= .45 and (not required or req_score >= .72) and not miss_req and score >= 64 \
            and not (years is None and (years_min is not None or SENIOR.search(job.title))):
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
        evidence_details=evidence_details,
    )


def rank_jobs(jobs: list[JobListing], resume: str, focus: str, years: int | None,
              scopes: set[str], country: str = 'India', city: str = '', max_results: int = 40) -> tuple[list[DetailedMatch], dict]:
    # Do not use a predefined role catalog. Evaluate real descriptions, and
    # keep uncertain and rejected listings distinct for exploration.
    seen: set[str] = set()
    candidate_skills = extract_resume_skills(resume)  # compute once, not once per retrieved vacancy
    candidate_profile = parse_resume(resume)  # examine the entire resume once
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
        item = evaluate_job(job, resume, focus, years, country, have_skills=candidate_skills, profile=candidate_profile)
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

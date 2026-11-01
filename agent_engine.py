"""RoleRoute 6: bounded, auditable search agent orchestration.

The AI can propose search terms and review job text, but *only* Python executes
approved job-feed tools. All tool actions are read-only. No unrestricted
website requests, paid-site bypass, account logins or application submissions.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from job_sources import DEFAULT_BOARDS, EXTRA_DEFAULT_BOARDS, JobListing, canonical_job_key
from matching_engine import rank_jobs, resume_focus, extract_resume_skills, clean_tokens

REGION_ORDER = ('India', 'International', 'Remote')
MAX_SOURCES = 28
MAX_RESULTS = 65


@dataclass
class AgentReport:
    profile: dict
    plan: dict
    jobs: list[JobListing]
    ranked: list
    stats: dict
    trace: list[str]
    errors: list[str]
    refinements: list[str]
    used_ai: bool
    ai_reviews: dict


def allowed_sources(scopes: set[str], extra: dict[str, list[str]] | None = None) -> list[tuple[str, str, str]]:
    """Return only registered public feeds; never model-supplied URLs."""
    extra = extra or {}
    out = []
    for region in REGION_ORDER:
        if region in scopes and region != 'Remote':
            out.extend((region, 'Greenhouse', board) for board in DEFAULT_BOARDS[region])
            out.extend((region, provider, board) for provider, board in EXTRA_DEFAULT_BOARDS[region])
    if 'Remote' in scopes:
        out.append(('Remote', 'Remotive', 'remote-feed'))
    for provider, boards in extra.items():
        if provider not in ('Greenhouse', 'Lever', 'Ashby', 'SmartRecruiters'):
            continue
        for board in boards[:4]:
            # Each extra board still passes the provider's existing ID validator.
            out.append(('Extra', provider, board))
    return list(dict.fromkeys(out))[:MAX_SOURCES]


def safe_search_terms(raw: list[str] | None, focus: str, skills: tuple[str, ...]) -> list[str]:
    """Accept model proposals only when grounded in candidate evidence."""
    evidence = set(clean_tokens(focus + ' ' + ' '.join(skills)))
    safe = []
    for term in (raw or []):
        if not isinstance(term, str):
            continue
        term = re.sub(r'[^\w\s+.#/-]', ' ', term).strip()[:65]
        words = set(clean_tokens(term))
        if not term or not words or not (words & evidence):
            continue
        if term.casefold() not in {x.casefold() for x in safe}:
            safe.append(term)
        if len(safe) >= 5:
            break
    if not safe:
        fallback = ' '.join(dict.fromkeys(clean_tokens(focus)))[:65]
        if not fallback:
            fallback = ' '.join(skills[:3])[:65]
        if fallback:
            safe.append(fallback)
    return safe


def source_batches(scopes: set[str], extra: dict[str, list[str]], preferred_regions: list[str] | None = None) -> tuple[list[tuple[str,str]], list[tuple[str,str]]]:
    """First pass is geographically diverse; second adds approved boards.

    Model can only order allowed regions, not fabricate new providers.
    """
    all_sources = allowed_sources(scopes, extra)
    order = [r for r in (preferred_regions or []) if r in scopes]
    order += [r for r in REGION_ORDER if r in scopes and r not in order]
    order.append('Extra')
    primary, secondary = [], []
    for region in order:
        entries = [(provider, board) for r, provider, board in all_sources if r == region]
        # Each region contributes at least two distinct employer feeds in pass 1.
        count = 2 if region not in ('Remote', 'Extra') else len(entries)
        primary += entries[:count]
        secondary += entries[count:]
    return list(dict.fromkeys(primary)), list(dict.fromkeys(secondary))


def distinct_jobs(jobs: list[JobListing]) -> list[JobListing]:
    seen = set()
    unique = []
    for job in jobs:
        key = canonical_job_key(job)
        if key and key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def relevant_count(ranked: list) -> int:
    return sum(item.category in ('Strong', 'Possible') for item in ranked)


def run_agent(
    resume: str, focus: str, years: int | None, scopes: set[str], country: str, city: str,
    extra: dict[str, list[str]],
    fetch_tool: Callable[[list[tuple[str, str]]], tuple[list[JobListing], list[str]]],
    *, ai_profile: Callable[[str, str], dict] | None = None,
    ai_plan: Callable[[str, str, set[str]], dict] | None = None,
    ai_refine: Callable[[dict, dict, list[str]], dict] | None = None,
    ai_review: Callable[[str, str, list], dict] | None = None,
    minimum_results: int = 5,
) -> AgentReport:
    """Run a maximum-two-feed-rounds, maximum-one-refinement agent.

    Missing sources and API exceptions fail closed to a visible warning. AI
    model responses never become network URLs, code, or arbitrary tool calls.
    """
    trace, errors, refinements = [], [], []
    skills = extract_resume_skills(resume)
    education = sorted(set(re.findall(r'\b(?:B\.?Tech|B\.?E\.?|M\.?Tech|M\.?E\.?|B\.?Sc|M\.?Sc|Bachelor(?:s)?|Master(?:s)?|Ph\.?D|Diploma|MBA)\b', resume, flags=re.I)))
    profile = {'skills': list(skills[:65]), 'career_focus': focus[:1000],
               'education_evidence': education[:12],
               'experience_years': years, 'country': country}
    if ai_profile:
        try:
            proposed = ai_profile(resume, focus)
            if isinstance(proposed, dict):
                # Additional model-suggested skills are suggestions only.
                validated = [s for s in proposed.get('verified_skills', [])
                             if isinstance(s, str) and s.casefold() in {k.casefold() for k in skills}]
                profile['verified_skills'] = validated[:40]
                profile['qualification_notes'] = str(proposed.get('qualification_notes', ''))[:300]
        except Exception:
            errors.append('AI resume understanding unavailable; local extraction was used.')
    trace.append(f'1 · Understood resume: {len(skills)} extracted skills; experience {years if years is not None else "unconfirmed"}.')

    plan = {'search_terms': safe_search_terms([], focus, skills), 'region_order': list(scopes),
            'query_reason': 'Candidate-derived career focus', 'start_with_extra_sources': False}
    used_ai = False
    if ai_plan:
        try:
            raw = ai_plan(resume, focus, scopes)
            if not isinstance(raw, dict):
                raise ValueError('Invalid plan')
            plan = {'search_terms': safe_search_terms(raw.get('search_terms'), focus, skills),
                    'region_order': [x for x in raw.get('region_order', []) if x in scopes][:3],
                    'query_reason': str(raw.get('query_reason', ''))[:200],
                    'start_with_extra_sources': bool(raw.get('start_with_extra_sources', False))}
            used_ai = True
        except Exception:
            errors.append('AI planning unavailable; candidate-based search plan was used.')
    trace.append('2 · Planned search terms: ' + ', '.join(plan['search_terms'][:3]))
    # Search terms influence the evidence-based relevance query, but cannot
    # introduce unrelated invented roles: safe_search_terms validates them.
    evaluation_focus = (focus + ' ' + ' '.join(plan['search_terms']))[:1450]
    primary, secondary = source_batches(scopes, extra, plan['region_order'])
    if plan['start_with_extra_sources']:
        # More aggressive first pass is still bounded by the allowed source registry.
        primary, secondary = primary + secondary, []
    trace.append(f'3 · Tool search round 1: {len(primary)} approved employer/remote feeds.')

    try:
        jobs, first_errors = fetch_tool(primary)
        errors.extend(first_errors)
    except Exception:
        jobs = []
        errors.append('First source round was temporarily unavailable.')
    jobs = distinct_jobs(jobs)
    ranked, stats = rank_jobs(jobs, resume, evaluation_focus, years, scopes, country, city, max_results=MAX_RESULTS)
    trace.append(f'4 · Compared {len(jobs)} distinct postings; {relevant_count(ranked)} potentially relevant results.')

    if relevant_count(ranked) < minimum_results and secondary:
        trace.append(f'5 · Few relevant matches: expanding to {len(secondary)} more approved feeds.')
        try:
            more_jobs, source_errors = fetch_tool(secondary)
            errors.extend(source_errors)
            jobs = distinct_jobs(jobs + more_jobs)
        except Exception:
            errors.append('Additional source round was temporarily unavailable.')
        ranked, stats = rank_jobs(jobs, resume, evaluation_focus, years, scopes, country, city, max_results=MAX_RESULTS)
        refinements.append('Expanded the employer-source coverage without relaxing required qualifications.')
    elif secondary:
        trace.append('5 · Enough relevant listings found in first round; expansion skipped.')
    else:
        trace.append('5 · All selected source feeds have been checked.')

    if relevant_count(ranked) < minimum_results:
        # Model can suggest alternative terms; we only use them if anchored to
        # actual resume evidence. No weakening of eligibility/experience checks.
        if ai_refine:
            try:
                suggestion = ai_refine(profile, stats, plan['search_terms'])
                alt = safe_search_terms(suggestion.get('search_terms', []), focus, skills)
                plan['refined_terms'] = alt
                # Refinement is an evidence-grounded re-query of the already
                # retrieved employer listings. Never bypass mandatory checks.
                alternative_focus = (focus + ' ' + ' '.join(alt))[:1450]
                revised_ranked, revised_stats = rank_jobs(jobs, resume, alternative_focus,
                    years, scopes, country, city, max_results=MAX_RESULTS)
                if relevant_count(revised_ranked) > relevant_count(ranked):
                    ranked, stats = revised_ranked, revised_stats
                    refinements.append('Re-ranked retrieved jobs using related candidate-backed terms.')
                plan['refined_applied'] = relevant_count(revised_ranked) > 0
                used_ai = True
                refinements.append('AI suggested related searches: ' + ', '.join(alt[:3]))
            except Exception:
                errors.append('AI search refinement unavailable; existing results retained.')
        trace.append('5 · No further approved feeds available; showing evidence-based results rather than inventing vacancies.')

    notes = {}
    if ai_review and ranked:
        try:
            notes = ai_review(resume, focus, ranked[:6])
            if not isinstance(notes, dict):
                notes = {}
            else:
                used_ai = True
        except Exception:
            errors.append('AI explanation unavailable; deterministic evidence is still shown.')
    trace.append(f'6 · Prepared explanations from actual job descriptions for {min(len(ranked), 6)} top listings.')
    return AgentReport(profile, plan, jobs, ranked, stats, trace, errors,
                       refinements, used_ai, notes)

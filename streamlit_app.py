"""RoleRoute v6 — auditable resume-to-vacancy AI agent.

Uses permitted employer feeds only. No prebuilt job-title role taxonomy; all
role matching comes from resume evidence and actual listings.
"""
from __future__ import annotations
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import html

import streamlit as st

from analyzer import extract_resume_text
from job_sources import (
    DEFAULT_BOARDS, EXTRA_DEFAULT_BOARDS, CAREER_PORTALS, JobListing, JobSourceError,
    fetch_greenhouse_jobs, fetch_lever_jobs, fetch_remotive_jobs,
    fetch_ashby_jobs, fetch_smartrecruiters_jobs, external_search_links,
    parse_board_names, valid_job_url,
)
from matching_engine import (extract_resume_skills, resume_focus, rank_jobs,
                             evaluate_job, safe_llm_profile)
from llm_agent import plan_search, explain_job_matches, interpret_resume, refine_search, AgentError
from agent_engine import run_agent
from resume_profile import parse_resume, dominant_topic

st.set_page_config(page_title='RoleRoute | Matching Jobs', page_icon='🎯', layout='wide')
st.markdown('''<style>
.block-container{max-width:1130px;padding-top:1.9rem}
.eyebrow{color:#2563eb;font-size:.82rem;font-weight:800;letter-spacing:.1em}
.hero{font-weight:820;font-size:clamp(2rem,4vw,3rem);line-height:1.2;margin:.3rem 0 .6rem}
.desc{font-size:1.07rem;color:#65748b;margin-bottom:1.1rem}
</style>''', unsafe_allow_html=True)

with st.sidebar:
    st.title('🎯 RoleRoute')
    st.caption('Resume-to-Job Agent · Version 6.1')
    st.divider()
    st.success('Live job feed search + description-based matching')
    st.write('✅ No predefined list of job roles')
    st.write('✅ Requirement-by-requirement evidence')
    st.write('✅ India, worldwide, and remote sources')
    st.write('✅ AI plan → tools → evaluate → refine → explain')
    st.caption('Jobs come from supported public sources only; always verify eligibility and availability.')

st.markdown('<div class="eyebrow">ROLEROUTE · RESUME-BASED JOB SEARCH</div>', unsafe_allow_html=True)
st.markdown('<div class="hero">Upload your resume. Discover matching jobs.</div>', unsafe_allow_html=True)
st.markdown('<div class="desc">A controlled job-search agent that reads your resume, searches approved live employer feeds, compares actual requirements and revises the search if necessary.</div>', unsafe_allow_html=True)

st.subheader('Upload resume')
st.caption('Your resume is processed by this Streamlit server, not sent to employer job feeds. This prototype has not completed a production privacy/security audit; do not upload sensitive personal documents.')
uploaded = st.file_uploader('Choose your PDF or DOCX resume', type=['pdf', 'docx'], help='Maximum supported file size: 5 MB')
resume = ''
resume_digest = ''
if uploaded is not None:
    try:
        file_bytes = uploaded.getvalue()
        if len(file_bytes) > 5 * 1024 * 1024:
            raise ValueError('The resume is larger than 5 MB. Please upload a smaller PDF or DOCX.')
        resume_digest = sha256(file_bytes).hexdigest()
        resume = extract_resume_text(file_bytes, uploaded.name)
        if not resume.strip():
            st.warning('No readable text was extracted. Try a text-based PDF or DOCX.')
    except ValueError as exc:
        st.error(str(exc))

@st.cache_data(ttl=1800, show_spinner=False)
def get_feed(provider: str, board: str) -> list[JobListing]:
    # Only public job source data is cached, never user resume content.
    functions = {'Greenhouse': fetch_greenhouse_jobs, 'Lever': fetch_lever_jobs,
                 'Ashby': fetch_ashby_jobs, 'SmartRecruiters': fetch_smartrecruiters_jobs}
    if provider not in functions:
        raise JobSourceError('Unsupported job source')
    return functions[provider](board)

@st.cache_data(ttl=21600, show_spinner=False)
def get_remote() -> list[JobListing]:
    return fetch_remotive_jobs()


def find_sources(scopes: set[str], extra: dict[str, list[str]]) -> list[tuple[str, str]]:
    result = []
    for region in ('India', 'International'):
        if region in scopes:
            result += [('Greenhouse', b) for b in DEFAULT_BOARDS[region]]
            result += EXTRA_DEFAULT_BOARDS[region]
    for provider, boards in extra.items():
        result += [(provider, board) for board in boards]
    if 'Remote' in scopes:
        result.append(('Remotive', 'remote-feed'))
    return list(dict.fromkeys(result))


def fetch_sources(sources: list[tuple[str, str]]) -> tuple[list[JobListing], list[str]]:
    data, errors = [], []
    if not sources:
        return data, errors
    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as pool:
        pending = {pool.submit(get_remote if provider == 'Remotive' else get_feed,
                               *(() if provider == 'Remotive' else (provider, board))): (provider, board)
                   for provider, board in sources}
        for future in as_completed(pending):
            provider, board = pending[future]
            try:
                data.extend(future.result())
            except Exception:
                errors.append(f'{provider}/{board}: not available or temporarily restricted')
    return data, errors


def display_match(item, ai_notes: dict | None = None) -> None:
    job = item.job
    with st.container(border=True):
        a, b = st.columns([5, 1])
        a.markdown('#### ' + html.escape(job.title))
        a.caption(f'{job.company} · {job.location} · {job.source}')
        b.metric('Fit estimate', f'{item.score}%')
        st.caption('Whole-resume evidence estimate, not hiring probability, confirmed eligibility, or an employer ATS score.')
        st.progress(item.score / 100)
        if item.found_required:
            st.write('**Required skills evidenced in resume:** ' + ', '.join(item.found_required))
        if item.missing_required:
            st.warning('**Mentioned as required but not evidenced in resume:** ' + ', '.join(item.missing_required))
        if item.found_preferred:
            st.write('**Preferred skills evidenced:** ' + ', '.join(item.found_preferred))
        if item.missing_preferred:
            st.caption('Preferred skills not found in resume: ' + ', '.join(item.missing_preferred))
        if item.found_mentioned:
            st.caption('Other shared technical terms: ' + ', '.join(item.found_mentioned))
        if item.role_evidence:
            st.write('**Why this role matches the resume:**')
            for explanation in item.role_evidence:
                st.write('• ' + explanation)
        if item.evidence_details:
            with st.expander('Resume sections considered for this match'):
                for section in item.evidence_details:
                    st.write('• ' + section)
        st.caption('Experience: ' + item.experience_note)
        st.caption('Location: ' + item.location_note)
        for message in item.warnings:
            st.caption('⚠️ ' + message)
        if ai_notes:
            st.info(f'**AI second opinion — {ai_notes["fit"]}:** {ai_notes["reason"]}\n\nCheck: {ai_notes["needs_check"]}')
        with st.expander('Show source job description (excerpt)'):
            st.write(job.description[:3500] if job.description else 'This feed did not supply a full description.')
        if job.last_updated:
            st.caption(f'Feed date: {job.last_updated} (not proof the position is still open)')
        if valid_job_url(job.url):
            st.link_button('🔗 View employer job page / Apply manually', job.url)
        st.caption('Apply directly on the employer site after checking that the vacancy is active and that you meet its requirements.')

if resume:
    # Each newly uploaded file starts a search automatically; searches are NOT
    # rerun on every Streamlit widget change, avoiding unnecessary API traffic.
    skills = extract_resume_skills(resume)
    candidate_profile = parse_resume(resume)
    suggested_focus = resume_focus(resume)[:1700]
    if candidate_profile.titles:
        st.write('**Career title(s) found in resume:** ' + ', '.join(candidate_profile.titles[:3]))
    else:
        st.caption('No explicit professional title found. Career relevance will be estimated from project, experience and summary evidence.')
    considered = [label for label, value in (
        ('Professional summary', candidate_profile.summary),
        ('Work/internship experience', candidate_profile.work_experience),
        ('Projects', candidate_profile.projects),
        ('Education', candidate_profile.education),
        ('Technical skills', candidate_profile.skills_section),
        ('Certifications', candidate_profile.certifications)) if value]
    st.caption('Resume information considered: ' + (', '.join(considered) if considered else 'Available resume text'))
    st.caption('Detected technical terms: ' + (', '.join(skills[:24]) if skills else 'No standard skills identified; compare with full job descriptions manually.'))

    with st.expander('Search preferences and optional AI (edit only if needed)'):
        focus = st.text_area(
            'Career titles, work, projects and skills detected from resume — you can correct them', value=suggested_focus,
            key=f'career_focus_{resume_digest[:16]}', max_chars=1700,
            help='Derived from resume text, not a fixed list of job roles.')
        left, right = st.columns(2)
        with left:
            scopes = st.multiselect('Search regions', ['India', 'International', 'Remote'],
                                    default=['India', 'International', 'Remote'])
            city = st.text_input('Preferred city (optional)', placeholder='Hyderabad or Bengaluru')
        with right:
            import re
            match_years = re.search(r'(?:experience\s*[:\-]\s*|(?:with|over|total of)\s+)(\d{1,2})\+?\s*(?:years?|yrs?)', resume, re.I)
            if not match_years:
                match_years = re.search(r'(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+|work\s+)?experience', resume, re.I)
            inferred_years = min(50, int(match_years.group(1))) if match_years else None
            options = [None, *range(51)]
            years = st.selectbox('Professional experience (confirm if known)', options,
                                 index=(inferred_years + 1 if inferred_years is not None else 0),
                                 format_func=lambda v: 'Not specified' if v is None else f'{v} years')
            country = st.text_input('Current country', value='India')
        st.caption('If experience is not specified, the app flags roles requiring years of experience for review instead of assuming you are a fresher.')
        enable_ai = st.checkbox('Enable full AI agent mode (Gemini)', value=False, help='Without an API key the app uses the free local planner and rule-based assessment. With AI enabled and consent, Gemini helps interpret, plan, refine and explain.')
        api_key = ''
        ai_model = 'gemini-2.5-flash'
        consent = False
        if enable_ai:
            st.warning('With consent, redacted career-title, summary, work, project, education and skill excerpts and public job descriptions are sent to Google Gemini. No full resume file is sent. Free-tier data may be used to improve Google products. Avoid including private identifiers in the career-focus box.')
            api_key = st.text_input('Gemini API key', type='password', help='Do not commit this to GitHub.')
            ai_model = st.selectbox('Gemini model', ['gemini-2.5-flash', 'gemini-2.5-flash-lite'])
            consent = st.checkbox('I consent to sending selected resume signals and public job description excerpts to Gemini')
            with st.expander('Preview the candidate data that AI may receive'):
                st.json(safe_llm_profile(resume, focus))
        with st.expander('Additional authorized public employer feeds (optional)'):
            st.caption('Company board IDs only; no private-site scraping or premium access bypass.')
            gh_extra = st.text_input('Greenhouse board IDs', key='gh')
            lever_extra = st.text_input('Lever board IDs', key='lev')
            ashby_extra = st.text_input('Ashby board IDs', key='ash')
            sr_extra = st.text_input('SmartRecruiters board IDs', key='sr')

    # The only prominent control is optional: upload triggers the first search.
    # Filter changes can be applied with this button, avoiding repeated API calls.
    refresh = st.button('🔄 Refresh matches using current preferences', use_container_width=True)
    if not scopes:
        st.warning('Select at least one search region in preferences.')

    # Include every relevant setting. Passwords are hashed, never displayed.
    setting_key = repr((focus, years, sorted(scopes), city, country, enable_ai,
                        sha256(api_key.encode()).hexdigest() if enable_ai and api_key else '',
                        ai_model, consent,
                        st.session_state.get('gh',''), st.session_state.get('lev',''),
                        st.session_state.get('ash',''), st.session_state.get('sr','')))
    context = sha256((resume_digest + setting_key).encode()).hexdigest()
    is_new_upload = resume_digest != st.session_state.get('v52_searched_upload_digest')
    search_requested = (is_new_upload or refresh)
    if search_requested and scopes:
        if enable_ai and (not api_key.strip() or not consent):
            st.warning('To use full AI-agent mode, enter a Gemini API key and explicitly consent, or turn AI mode off for the free deterministic workflow.')
        else:
            try:
                extra = {
                    'Greenhouse': parse_board_names(st.session_state.get('gh', '')),
                    'Lever': parse_board_names(st.session_state.get('lev', '')),
                    'Ashby': parse_board_names(st.session_state.get('ash', '')),
                    'SmartRecruiters': parse_board_names(st.session_state.get('sr', '')),
                }
            except JobSourceError as exc:
                st.error(str(exc))
            else:
                # The AI plans *which registered tools to call*, but never
                # receives arbitrary network access or application permissions.
                profile_fn = (lambda r, f: interpret_resume(r, f, api_key, ai_model)) if enable_ai else None
                plan_fn = (lambda r, f, regions: plan_search(r, f, regions, api_key, ai_model)) if enable_ai else None
                refine_fn = (lambda p, stats, terms: refine_search(p, stats, terms, api_key, ai_model)) if enable_ai else None
                review_fn = (lambda r, f, matches: explain_job_matches(r, f, matches, api_key, ai_model)) if enable_ai else None
                with st.spinner('Agent: understanding resume → planning → using job search tools → evaluating → refining...'):
                    report = run_agent(
                        resume, focus, years, set(scopes), country, city, extra, fetch_sources,
                        ai_profile=profile_fn, ai_plan=plan_fn,
                        ai_refine=refine_fn, ai_review=review_fn,
                    )
                st.session_state.v52_search = {
                    'fingerprint': context, 'jobs': report.jobs,
                    'ranked': report.ranked, 'stats': report.stats,
                    'errors': report.errors, 'plan': report.plan,
                    'refinements': report.refinements, 'trace': report.trace,
                    'profile': report.profile, 'reviews': report.ai_reviews,
                    'used_ai': report.used_ai, 'requested_ai': enable_ai,
                }
                st.session_state.v52_searched_upload_digest = resume_digest

    results = st.session_state.get('v52_search')
    if results and results['fingerprint'] != context:
        st.info('Search preferences changed. Click “Refresh matches using current preferences” to update the results.')
    elif results:
        st.subheader('Matching jobs for your resume')
        st.caption('Agent mode: ' + ('Gemini-assisted reasoning with approved tools' if results.get('used_ai') else 'Free rule-based tool workflow (enable Gemini for LLM reasoning)'))
        jobs, ranked, stats = results['jobs'], results['ranked'], results['stats']
        a, b, c, d = st.columns(4)
        a.metric('Retrieved postings', stats.get('retrieved', 0))
        b.metric('Strong matches', stats.get('Strong', 0))
        c.metric('Possible matches', stats.get('Possible', 0))
        d.metric('Needs review', stats.get('Review / conflict', 0))
        st.caption('Scores are provisional evidence-based estimates, never guaranteed eligibility, hiring probability, or a verified employment offer.')
        with st.expander('See what the agent did — six-step decision log', expanded=False):
            for step in results.get('trace', []):
                st.write(step)
            if results.get('refinements'):
                st.write('**Search adjustments:**')
                for step in results['refinements']:
                    st.write('• ' + step)
            if results.get('errors'):
                st.caption('Unavailable steps were handled safely: ' + '; '.join(results['errors']))
        if not ranked:
            st.warning('No matching job descriptions were found in these sources. Try another region, check your experience setting, or refresh the search.')
        recommended = [(idx, item) for idx, item in enumerate(ranked)
                       if item.category in ('Strong', 'Possible')]
        if recommended:
            st.markdown('### Relevant job opportunities')
            for idx, item in recommended[:20]:
                display_match(item, results['reviews'].get(idx) if results['used_ai'] else None)
            if len(recommended) > 20:
                st.caption(f'{len(recommended) - 20} further relevant results omitted from this page to keep it readable.')
        else:
            st.warning('No confidently relevant vacancies were found in the connected job feeds for this resume. This does not mean no suitable jobs exist.')
        review_items = [(idx, item) for idx, item in enumerate(ranked)
                        if item.category == 'Review / conflict']
        if review_items:
            with st.expander(f'Other opportunities needing review ({len(review_items)})'):
                st.caption('These listings may have an experience, location or career-fit conflict. They are not recommended as confirmed matches.')
                for idx, item in review_items[:12]:
                    display_match(item, results['reviews'].get(idx) if results['used_ai'] else None)
        with st.expander('Search details and source diagnostics'):
            provider_counts = Counter(j.source for j in jobs)
            st.caption('Retrieved by source: ' + (' · '.join(f'{s}: {v}' for s, v in sorted(provider_counts.items())) or 'none'))
            if results['plan']:
                plan = results['plan']
                st.write('**AI search plan:** ' + ', '.join(plan['search_terms']))
                st.caption(plan['query_reason'])
            if results['errors']:
                st.write('Some job feeds were unavailable:')
                for message in results['errors']:
                    st.write('- ' + message)
            st.json(stats)

    # Advanced tools are available without overwhelming the primary upload/results flow.
    with st.expander('Optional: compare a job posting or search more websites'):
        st.caption('You may compare a public/private job description you are authorized to view. RoleRoute does not bypass premium-site restrictions.')
        with st.form('manual_job'):
            title = st.text_input('Job title')
            company = st.text_input('Employer')
            location = st.text_input('Location')
            description = st.text_area('Paste job description and requirements', height=140)
            url = st.text_input('Official posting link (optional)')
            compare = st.form_submit_button('Compare this job with my resume')
        if compare:
            if not title.strip() or len(description.strip()) < 30:
                st.warning('Enter a job title and at least 30 characters of job requirements.')
            else:
                test_job = JobListing(source='User-supplied (not independently verified)',
                                      company=company[:100] or 'Not provided', job_id='manual',
                                      title=title[:150], location=location[:150] or 'Unspecified',
                                      description=description[:24000],
                                      url=url if valid_job_url(url) else '',
                                      is_remote='remote' in location.lower())
                review = evaluate_job(test_job, resume, focus, years, country)
                st.write(f'**Provisional category:** {review.category}')
                display_match(review)
        st.markdown('**Other official job-site searches**')
        st.caption('These links run searches on external sites. Their vacancies have not been retrieved or ranked by RoleRoute.')
        from matching_engine import focus_search_query
        search_role = (results['plan']['search_terms'][0]
                       if results and results.get('plan') and results['plan']['search_terms']
                       else focus_search_query(focus))[:80]
        links = external_search_links(search_role, city, country)
        for start_idx in range(0, len(links), 2):
            cols = st.columns(2)
            for col, (name, note, link) in zip(cols, links[start_idx:start_idx + 2]):
                with col:
                    st.link_button(f'Open {name}', link, use_container_width=True)
                    st.caption(note)
        with st.expander(f'Official employer career sites ({len(CAREER_PORTALS)})'):
            for name, link in CAREER_PORTALS:
                st.link_button(f'{name} careers', link)
else:
    # No demo resumes or sample instructions: user simply uploads a file.
    st.session_state.pop('v52_searched_upload_digest', None)

st.divider()
st.caption('RoleRoute v6.1 · Whole-resume matching · Read-only bounded agent · Verify all vacancies before applying · No auto-apply or premium access bypass.')
